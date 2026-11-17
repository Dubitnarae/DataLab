"""측정 이력 DB(SQLite) + 원본 저장소.

문서\\DataLab_Data\\datalab.sqlite 와 originals\\<sha256>.<확장자>. 같은 원본 파일은 SHA256으로 한 번만 저장한다.
네트워크 드라이브(RaiDrive/WebDAV)에 직접 두지 않는다(CLAUDE.md) — NAS는 백업·병합 대상.
"""

from __future__ import annotations

import hashlib
import json
import platform
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


def _copy_verified(src: Path, dest: Path, digest: str):
    """dest가 없으면 src를 복사하고 SHA256을 대조한다. 다르면 지우고 OSError."""
    if dest.exists():
        return
    tmp = dest.with_suffix(dest.suffix + ".part")  # 복사 도중 끊겨도 반쪽 파일이 원본 행세를 하지 않게
    shutil.copyfile(src, tmp)
    if sha256(tmp) != digest:  # 이 PC는 큰 파일 비트 깨짐 이력이 있음
        tmp.unlink()
        raise OSError(f"복사본이 원본과 다릅니다: {src.name}")
    tmp.replace(dest)


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
        _copy_verified(path, self.root / "originals" / f"{digest}{path.suffix.lower()}", digest)
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

    def samples(self, text: str = "", kind: str | None = None) -> list[dict]:
        """시료 목록(이름순): id·name·composition·process·lot·memo·tags(쉼표로 이음)·n(측정 수).

        text: 띄어쓰기로 나눈 단어가 모두 이름·조성·공정·로트·메모·태그·원본 파일 이름 어딘가에 든 시료만(대소문자 무시).
        kind: 'VSM'·'XRD'면 그 종류 측정이 있는 시료만.
        """
        rows = self.con.execute(
            "SELECT s.id, s.name, s.composition, s.process, s.lot, s.memo,"
            " (SELECT GROUP_CONCAT(tag, ', ') FROM (SELECT tag FROM tags WHERE sample_id = s.id ORDER BY tag)),"
            " (SELECT COUNT(*) FROM measurements WHERE sample_id = s.id),"
            " (SELECT GROUP_CONCAT(file_name, ' ') FROM measurements WHERE sample_id = s.id)"
            " FROM samples s WHERE ? IS NULL OR EXISTS"
            " (SELECT 1 FROM measurements WHERE sample_id = s.id AND kind = ?) ORDER BY s.name",
            (kind, kind)).fetchall()
        keys = ("id", "name", "composition", "process", "lot", "memo", "tags", "n")
        words = text.casefold().split()
        out = []
        for r in rows:
            hay = " ".join(str(v) for v in (*r[1:7], r[8]) if v).casefold()
            if all(w in hay for w in words):
                out.append(dict(zip(keys, r)))
        return out

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

    def compare(self, sample_ids: list[int], kind: str | None = None) -> tuple[list[str], list[list]]:
        """결과 비교표: 측정 한 줄씩(시료 이름순). 앞 열은 시료 정보, 뒤 열은 결과 'key (단위)'(처음 나온 순서).

        같은 key라도 단위가 다르면 다른 열(원본 단위 그대로 — 변환하지 않음). 값은 DB 값 그대로(숫자는 숫자).
        """
        if not sample_ids:
            return [], []
        marks = ",".join("?" * len(sample_ids))
        meas = self.con.execute(
            "SELECT m.id, s.name, s.composition, s.process, s.lot,"
            " (SELECT GROUP_CONCAT(tag, ', ') FROM (SELECT tag FROM tags WHERE sample_id = s.id ORDER BY tag)),"
            " m.kind, m.file_name, m.measured_at FROM measurements m JOIN samples s ON s.id = m.sample_id"
            f" WHERE s.id IN ({marks}) AND (? IS NULL OR m.kind = ?) ORDER BY s.name, m.created_at, m.id",
            (*sample_ids, kind, kind)).fetchall()
        cols: dict[str, int] = {}
        vals: dict[int, dict[str, object]] = {}
        ver: dict[int, str] = {}
        for mid, key, value, unit, av in self.con.execute(
                f"SELECT measurement_id, key, value, unit, analysis_version FROM results"
                f" WHERE measurement_id IN ({','.join('?' * len(meas))}) ORDER BY rowid", [m[0] for m in meas]):
            head = f"{key} ({unit})" if unit else key
            cols.setdefault(head, len(cols))
            vals.setdefault(mid, {})[head] = value
            ver[mid] = av
        heads = ["시료", "조성", "공정", "로트", "태그", "종류", "원본 파일", "측정일", "해석 버전", *cols]
        rows = [[*m[1:], ver.get(m[0]), *(vals.get(m[0], {}).get(h) for h in cols)] for m in meas]
        return heads, rows

    def backup(self, dest: str | Path) -> Path:
        """dest 안 DataLab_Backup 폴더에 날짜별 DB 사본 + originals(없는 것만, SHA 대조). 돌려줌: DB 사본 경로.

        DB는 로컬에서 SQLite 백업 API로 떠서 복사한다(WebDAV 위에서 SQLite를 직접 쓰지 않음).
        """
        out = Path(dest) / "DataLab_Backup"
        (out / "originals").mkdir(parents=True, exist_ok=True)
        for f in (self.root / "originals").iterdir():
            if f.suffix != ".part":
                _copy_verified(f, out / "originals" / f.name, f.stem)
        tmp = self.root / "backup.tmp.sqlite"
        tmp.unlink(missing_ok=True)
        snap = sqlite3.connect(tmp)
        self.con.backup(snap)
        snap.close()
        target = out / f"datalab_{platform.node()}_{datetime.now():%Y%m%d_%H%M%S}.sqlite"
        target.unlink(missing_ok=True)  # 같은 PC에서 같은 초에 또 떴으면 새 사본으로
        try:
            _copy_verified(tmp, target, sha256(tmp))
        finally:
            tmp.unlink()
        return target

    def merge(self, src: str | Path) -> dict[str, int]:
        """다른 PC의 DB(백업 사본)를 합친다. 원본은 src 옆 originals 폴더에서 가져온다.

        측정은 원본 SHA256 기준 — 이미 있으면 건너뜀(이 PC 값 유지). 시료는 이름 기준, 이 PC에서 빈 칸만 채우고
        태그는 합집합. 원본이 하나라도 없으면 DB는 그대로 두고 OSError.
        돌려줌: {'samples': 새 시료, 'measurements': 새 측정, 'skipped': 이미 있던 측정}.
        """
        src = Path(src)
        tmp = self.root / "merge.tmp.sqlite"  # 네트워크 드라이브의 SQLite를 직접 열지 않고 로컬 사본으로 읽음
        shutil.copyfile(src, tmp)
        try:
            o = sqlite3.connect(tmp)
            try:
                samples = o.execute("SELECT id, name, composition, process, lot, memo, created_at FROM samples").fetchall()
                tags = o.execute("SELECT sample_id, tag FROM tags").fetchall()
                meas = o.execute("SELECT id, sample_id, kind, file_sha256, file_name, measured_at, instrument,"
                                 " raw_meta_json, created_at FROM measurements").fetchall()
                results = o.execute("SELECT measurement_id, key, value, unit, analysis_version FROM results").fetchall()
            finally:
                o.close()
        finally:
            tmp.unlink()
        have = {r[0] for r in self.con.execute("SELECT file_sha256 FROM measurements")}
        new = [m for m in meas if m[3] not in have]
        for m in new:  # 원본부터 — 없으면 DB를 건드리기 전에 멈춤
            name = f"{m[3]}{Path(m[4]).suffix.lower()}"
            if not (src.parent / "originals" / name).exists() and not (self.root / "originals" / name).exists():
                raise OSError(f"백업에 원본 사본이 없습니다: {m[4]} ({name})")
            _copy_verified(src.parent / "originals" / name, self.root / "originals" / name, m[3])
        name_of = {sid: n for sid, n, *_ in samples}
        n_before = self.counts()[0]
        with self.con:
            for _, name, *fields, created in samples:
                self.con.execute("INSERT OR IGNORE INTO samples (name, created_at) VALUES (?, ?)", (name, created))
                for f, v in zip(self.SAMPLE_FIELDS, fields):  # 열 이름은 허용 목록에서만
                    self.con.execute(f"UPDATE samples SET {f} = COALESCE({f}, ?) WHERE name = ?", (v, name))
            self.con.executemany("INSERT OR IGNORE INTO tags (sample_id, tag) SELECT id, ? FROM samples WHERE name = ?",
                                 [(t, name_of[sid]) for sid, t in tags])
            res_of: dict[int, list] = {}
            for mid, *r in results:
                res_of.setdefault(mid, []).append(r)
            for oid, osid, *rest in new:
                sid = self.con.execute("SELECT id FROM samples WHERE name = ?", (name_of[osid],)).fetchone()[0]
                mid = self.con.execute(
                    "INSERT INTO measurements (sample_id, kind, file_sha256, file_name, measured_at, instrument,"
                    " raw_meta_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (sid, *rest)).lastrowid
                self.con.executemany("INSERT INTO results (measurement_id, key, value, unit, analysis_version)"
                                     " VALUES (?, ?, ?, ?, ?)", [(mid, *r) for r in res_of.get(oid, [])])
        return {"samples": self.counts()[0] - n_before, "measurements": len(new), "skipped": len(meas) - len(new)}


def write_xlsx(path: str | Path, heads: list[str], rows: list[list]):
    """비교표를 Excel로 저장한다. 첫 줄 고정·자동 필터."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "결과 비교"
    ws.append(heads)
    for r in rows:
        ws.append(r)
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "B2"
    if rows:
        ws.auto_filter.ref = ws.dimensions
    for i, h in enumerate(heads, 1):
        width = max([len(str(h))] + [len(str(r[i - 1])) for r in rows if r[i - 1] is not None])
        ws.column_dimensions[ws.cell(1, i).column_letter].width = min(width + 2, 50)
    wb.save(path)
