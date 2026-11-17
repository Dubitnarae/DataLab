"""M5 ⑤ NAS 백업·병합: 집·회사 PC를 서로 병합해도 중복이 없어야 한다."""

import pytest

from datalab import db


def _file(tmp_path, name, text):
    p = tmp_path / "src" / name
    p.parent.mkdir(exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_backup_merge_both_ways_no_duplicates(tmp_path):
    a, b, nas = db.Store(tmp_path / "home"), db.Store(tmp_path / "office"), tmp_path / "nas"
    shared = _file(tmp_path, "shared.csv", "same")
    a.add_measurement(shared, "VSM", "합금A", {"Hc": (2.5, "Oe")}, "vsm-1")
    a.add_measurement(_file(tmp_path, "a.csv", "a"), "VSM", "합금A", {"Hc": (3.0, "Oe")}, "vsm-1")
    a.update_sample(1, "composition", "Fe78Si9B13")
    a.update_sample(1, "tags", "리본")
    b.add_measurement(shared, "VSM", "합금A", {"Hc": (9.9, "Oe")}, "vsm-1")  # 같은 원본, 다른 값
    b.add_measurement(_file(tmp_path, "b.xy", "b"), "XRD", "합금B", {"판정": ("비정질", "")}, "xrdcheck-0.8.0")
    b.update_sample(1, "composition", "회사값")
    b.update_sample(1, "tags", "열처리")

    r = b.merge(a.backup(nas))
    assert r == {"samples": 0, "measurements": 1, "skipped": 1}
    assert b.merge(a.backup(nas)) == {"samples": 0, "measurements": 0, "skipped": 2}  # 두 번 해도 그대로
    assert a.merge(b.backup(nas)) == {"samples": 1, "measurements": 1, "skipped": 2}

    for s in (a, b):
        assert s.counts() == (2, 3)
        rows = {x["name"]: x for x in s.samples()}
        assert rows["합금A"]["tags"] == "리본, 열처리" and rows["합금B"]["n"] == 1
        assert len(list((s.root / "originals").iterdir())) == 3
        heads, table = s.compare([x["id"] for x in s.samples()])
        assert len(table) == 3
    assert {x["name"]: x["composition"] for x in a.samples()}["합금A"] == "Fe78Si9B13"  # 이 PC 값 유지
    assert {x["name"]: x["composition"] for x in b.samples()}["합금A"] == "회사값"
    hc = b.con.execute("SELECT r.value FROM results r JOIN measurements m ON m.id = r.measurement_id"
                       " WHERE m.file_name = 'shared.csv'").fetchone()[0]
    assert hc == 9.9
    assert len(list((nas / "DataLab_Backup" / "originals").iterdir())) == 3


def test_merge_missing_original_leaves_db(tmp_path):
    a, b = db.Store(tmp_path / "home"), db.Store(tmp_path / "office")
    a.add_measurement(_file(tmp_path, "a.csv", "a"), "VSM", "합금A", {"Hc": (1.0, "Oe")}, "vsm-1")
    bak = a.backup(tmp_path / "nas")
    for f in (bak.parent / "originals").iterdir():
        f.unlink()
    with pytest.raises(OSError):
        b.merge(bak)
    assert b.counts() == (0, 0)


def test_db_dialog_backup_merge(qtbot, tmp_path):
    from datalab.gui.db_dialog import DbDialog

    a = db.Store(tmp_path / "home")
    a.add_measurement(_file(tmp_path, "a.csv", "a"), "VSM", "합금A", {"Hc": (1.0, "Oe")}, "vsm-1")
    a.close()
    d = DbDialog(None, tmp_path / "home")
    qtbot.addWidget(d)
    assert d.backup(str(tmp_path / "nas"))
    bak = next((tmp_path / "nas" / "DataLab_Backup").glob("datalab_*.sqlite"))
    e = DbDialog(None, tmp_path / "office")
    qtbot.addWidget(e)
    assert e.merge(str(bak)) == {"samples": 1, "measurements": 1, "skipped": 0}
    assert e.samples.rowCount() == 1 and "새 측정 1개" in e.info.text()
