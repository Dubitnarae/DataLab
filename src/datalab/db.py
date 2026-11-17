"""측정 이력 DB(SQLite) + 원본 저장소.

문서\\DataLab_Data\\datalab.sqlite 와 originals\\<sha256>.<확장자>. 같은 원본 파일은 SHA256으로 한 번만 저장한다.
네트워크 드라이브(RaiDrive/WebDAV)에 직접 두지 않는다(CLAUDE.md) — NAS는 백업·병합 대상.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

DATA_DIR = Path.home() / "Documents" / "DataLab_Data"

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, composition TEXT, process TEXT, lot TEXT, memo TEXT,
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY, sample_id INTEGER NOT NULL REFERENCES samples(id), kind TEXT NOT NULL,
    file_sha256 TEXT NOT NULL UNIQUE, file_name TEXT NOT NULL, measured_at TEXT, instrument TEXT,
    raw_meta_json TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS results (
    measurement_id INTEGER NOT NULL REFERENCES measurements(id) ON DELETE CASCADE, key TEXT NOT NULL,
    value, unit TEXT, analysis_version TEXT NOT NULL, PRIMARY KEY (measurement_id, key));
CREATE TABLE IF NOT EXISTS tags (
    sample_id INTEGER NOT NULL REFERENCES samples(id), tag TEXT NOT NULL, PRIMARY KEY (sample_id, tag));
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, root: str | Path = DATA_DIR):
        self.root = Path(root)
        (self.root / "originals").mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.root / "datalab.sqlite")
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.executescript(SCHEMA)

    def close(self):
        self.con.close()

    def add_measurement(self, path: str | Path, kind: str, sample: str, results: dict[str, tuple],
                        analysis_version: str, measured_at: str | None = None, instrument: str | None = None,
                        meta: dict | None = None) -> tuple[int, bool]:
        """원본을 복사하고 측정·결과를 기록한다. results = {key: (value, unit)}.

        같은 원본(SHA256)이 이미 있으면 측정은 그대로 두고 결과만 새 값으로 바꾼다. 돌려줌: (측정 id, 새로 넣었나).
        """
        path = Path(path)
        digest = sha256(path)
        dest = self.root / "originals" / f"{digest}{path.suffix.lower()}"
        if not dest.exists():
            tmp = dest.with_suffix(dest.suffix + ".part")  # 복사 도중 끊겨도 반쪽 파일이 원본 행세를 하지 않게
            shutil.copyfile(path, tmp)
            if sha256(tmp) != digest:  # 이 PC는 큰 파일 비트 깨짐 이력이 있음
                tmp.unlink()
                raise OSError(f"원본 복사본이 원본과 다릅니다: {path.name}")
            tmp.replace(dest)
        with self.con:
            self.con.execute("INSERT OR IGNORE INTO samples (name, created_at) VALUES (?, ?)", (sample, _now()))
            sid = self.con.execute("SELECT id FROM samples WHERE name = ?", (sample,)).fetchone()[0]
            row = self.con.execute("SELECT id FROM measurements WHERE file_sha256 = ?", (digest,)).fetchone()
            new = row is None
            if new:
                mid = self.con.execute(
                    "INSERT INTO measurements (sample_id, kind, file_sha256, file_name, measured_at, instrument,"
                    " raw_meta_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (sid, kind, digest, path.name, measured_at, instrument,
                     json.dumps(meta or {}, ensure_ascii=False, default=str), _now())).lastrowid
            else:
                mid = row[0]
                self.con.execute("DELETE FROM results WHERE measurement_id = ?", (mid,))
            self.con.executemany(
                "INSERT INTO results (measurement_id, key, value, unit, analysis_version) VALUES (?, ?, ?, ?, ?)",
                [(mid, k, v, u, analysis_version) for k, (v, u) in results.items() if v is not None])
        return mid, new

    def counts(self) -> tuple[int, int]:
        """(시료 수, 측정 수)."""
        return (self.con.execute("SELECT COUNT(*) FROM samples").fetchone()[0],
                self.con.execute("SELECT COUNT(*) FROM measurements").fetchone()[0])

    def samples(self) -> list[dict]:
        """시료 목록(이름순): id·name·composition·process·lot·memo·tags(쉼표로 이음)·n(측정 수)."""
        rows = self.con.execute(
            "SELECT s.id, s.name, s.composition, s.process, s.lot, s.memo,"
            " (SELECT GROUP_CONCAT(tag, ', ') FROM (SELECT tag FROM tags WHERE sample_id = s.id ORDER BY tag)),"
            " (SELECT COUNT(*) FROM measurements WHERE sample_id = s.id) FROM samples s ORDER BY s.name").fetchall()
        keys = ("id", "name", "composition", "process", "lot", "memo", "tags", "n")
        return [dict(zip(keys, r)) for r in rows]

    SAMPLE_FIELDS = ("composition", "process", "lot", "memo")

    def update_sample(self, sample_id: int, field: str, value: str):
        """시료 정보 한 칸을 바꾼다. field = SAMPLE_FIELDS 또는 'tags'(쉼표로 나눈 태그 전체를 바꿈)."""
        value = value.strip()
        with self.con:
            if field == "tags":
                self.con.execute("DELETE FROM tags WHERE sample_id = ?", (sample_id,))
                tags = {t.strip() for t in value.split(",") if t.strip()}
                self.con.executemany("INSERT INTO tags (sample_id, tag) VALUES (?, ?)", [(sample_id, t) for t in tags])
            elif field in self.SAMPLE_FIELDS:  # 열 이름을 SQL에 넣으므로 허용 목록만
                self.con.execute(f"UPDATE samples SET {field} = ? WHERE id = ?", (value or None, sample_id))
            else:
                raise ValueError(field)

    def measurements(self, sample_id: int) -> list[dict]:
        """시료의 측정 목록: id·kind·file_name·measured_at·created_at·path(원본 사본)."""
        rows = self.con.execute("SELECT id, kind, file_name, measured_at, created_at, file_sha256 FROM measurements"
                                " WHERE sample_id = ? ORDER BY created_at, id", (sample_id,)).fetchall()
        return [{"id": i, "kind": k, "file_name": f, "measured_at": ma, "created_at": c,
                 "path": self.root / "originals" / f"{sha}{Path(f).suffix.lower()}"} for i, k, f, ma, c, sha in rows]
