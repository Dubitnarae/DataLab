"""자동 업데이트: 공유 폴더 출처로 새 버전 찾기 → SHA256 확인 → 풀기 → 파일 바꾸기(네트워크 없이)."""

import hashlib
import zipfile

import pytest

from datalab import __version__, updater


def _release_folder(tmp_path, ver="99.0.0", bad_hash=False):
    src = tmp_path / "src" / "DataLab"
    src.mkdir(parents=True)
    (src / "DataLab.exe").write_bytes(b"new")
    folder = tmp_path / "share"
    folder.mkdir()
    zp = folder / f"DataLab_v{ver}.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.write(src / "DataLab.exe", "DataLab/DataLab.exe")
    h = "0" * 64 if bad_hash else hashlib.sha256(zp.read_bytes()).hexdigest()
    (folder / f"{zp.name}.sha256").write_text(f"{h}  {zp.name}", encoding="ascii")
    (folder / "DataLab_v0.0.1.zip").write_bytes(b"old")  # 옛 버전은 무시돼야 함
    return folder


def test_version_and_config(tmp_path):
    assert updater.is_newer("0.10.0", "0.9.9") and not updater.is_newer(__version__)
    assert updater.load_config(tmp_path)["github_repo"] == "Dubitnarae/DataLab"
    (tmp_path / "update.json").write_text('{"folder": "X:/dl", "모름": 1}', encoding="utf-8")
    cfg = updater.load_config(tmp_path)
    assert cfg["folder"] == "X:/dl" and "모름" not in cfg


def test_folder_update_and_replace(tmp_path, monkeypatch):
    monkeypatch.setenv("DATALAB_UPDATE_DIR", str(tmp_path / "upd"))
    rel = updater.check({"folder": str(_release_folder(tmp_path))})
    assert rel.version == "99.0.0"
    app = updater.prepare(rel)
    target = tmp_path / "install"
    target.mkdir()
    (target / "DataLab.exe").write_bytes(b"old")
    (target / "내 파일.txt").write_text("남아야 함", encoding="utf-8")
    updater.replace_files(app, target, tmp_path / "backup")
    assert (target / "DataLab.exe").read_bytes() == b"new"
    assert (target / "내 파일.txt").exists() and (tmp_path / "backup" / "DataLab.exe").read_bytes() == b"old"


def test_bad_sha_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATALAB_UPDATE_DIR", str(tmp_path / "upd"))
    rel = updater.check({"folder": str(_release_folder(tmp_path, bad_hash=True))})
    with pytest.raises(updater.UpdateError, match="SHA256"):
        updater.prepare(rel)
