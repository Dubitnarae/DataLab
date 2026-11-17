"""VSM 읽기·해석. 합성 루프로 장비 계산식(AI 오피스 vsm.ts 실측 확인)을 재현하는지 본다."""

import csv
from pathlib import Path

import numpy as np
import pytest

from datalab.analysis.vsm import analyze_loop, compare_device, dmdh, high_field_slope
from datalab.io import load_any
from datalab.io.vsm import UnsupportedVsmFile, read_vsm


def loop(hc: float, shift: float = 0.0, hmax: float = 100.0):
    """내려가는 가지는 H=shift−hc, 올라오는 가지는 H=shift+hc에서 M=0. M은 ±50에서 포화."""
    down = np.arange(hmax, -hmax - 1, -1.0)
    up = -down
    m = lambda h, c: np.clip(4 * (h - c), -50, 50)  # noqa: E731
    return np.r_[down, up], np.r_[m(down, shift - hc), m(up, shift + hc)]


def lakeshore(tmp_path: Path, device: dict, h, m, bom=False) -> Path:
    head = ("#RUN ON SOFTWARE VERSION:\n2.2\n#SAMPLE SETTINGS\nID: X1\nMass: 16.7000E-3 g\n#EXTRACTED PARAMETERS\n"
            f"Intrinsic coercivity: {device['hc']} Oe\nRemanent mass magnetization: {device['mr']}emu/g\n"
            f"Saturation mass magnetization : {device['ms']}emu/g\nSTART TIME: 07/16/2026\n#DATA: 2 Corrections\n"
            "##DATA TABLE Mass magnetization (M) [emu/g] vs Field [Oe]\n"
            "Step,Iteration,Segment,Field [Oe],Mass magnetization (M) [emu/g],Time Stamp [s],Field Status,"
            "Mass magnetization (M) Status,\n")
    body = "\n".join(f"2,0,0,{a},{b},0,GOOD,GOOD," for a, b in zip(h, m))
    p = tmp_path / "a.csv"
    p.write_text((chr(0xFEFF) if bom else "") + head + body, encoding="utf-8")
    return p


def test_lakeshore_read_and_device_match(tmp_path):
    d = read_vsm(lakeshore(tmp_path, {"hc": 2.5, "mr": 10, "ms": 50}, *loop(2.5)))
    assert (d.file_format, d.sample_id, d.m_unit, d.meta["mass_g"]) == ("lakeshore_csv", "X1", "emu/g", 0.0167)
    assert d.device == {"Hc": 2.5, "Mr": 10, "Ms": 50}
    r = analyze_loop(d.h, d.m)
    assert r["Hc"] == pytest.approx(2.5) and r["Hc_half"] == pytest.approx(2.5)
    assert r["Mr"] == pytest.approx(10) and r["Ms"] == pytest.approx(50) and r["SQ"] == pytest.approx(0.2)
    assert r["shifted"] is False and r["H_max"] == 100
    assert compare_device(r, d.device) == []


def test_bom_and_mismatch(tmp_path):
    d = read_vsm(lakeshore(tmp_path, {"hc": 9, "mr": 10, "ms": 70}, *loop(2.5), bom=True))
    msg = "; ".join(compare_device(analyze_loop(d.h, d.m), d.device))
    assert "Hc 장비 9" in msg and "Ms 장비 70" in msg and "Mr" not in msg


def test_shifted_loop_reports_half_width_and_bias():
    r = analyze_loop(*loop(2.5, shift=6))
    assert r["Hc"] == pytest.approx(6)  # 장비식(절댓값 평균)은 치우침만큼 커진다
    assert r["Hc_half"] == pytest.approx(2.5) and r["H_bias"] == pytest.approx(6) and r["shifted"]


def test_field_offset_correction():
    h, m = loop(2.5, shift=0.4)
    r = analyze_loop(h, m, field_offset=0.4)
    assert r["Hc"] == pytest.approx(2.5) and r["H_bias"] == pytest.approx(0) and r["field_offset"] == 0.4


def test_ideas_txt_and_generic(tmp_path):
    h, m = loop(2.5)
    rows = "\n".join(f"{a}\t{b}" for a, b in zip(h, m))
    p = tmp_path / "b.txt"
    p.write_text(f"Start Time:  10/14/2024\nSample ID:     X2\n\n***DATA***\n\nField(Oe)\t Moment/Mass(emu/g)\t\n{rows}")
    d = read_vsm(p)
    assert (d.file_format, d.sample_id, d.h_unit, d.m_unit, d.device) == ("ideas_txt", "X2", "Oe", "emu/g", {})
    g = tmp_path / "c.dat"
    with g.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["H [Oe]", "M [emu]"])
        w.writerows(zip(h, m))
    d = read_vsm(g)
    assert (d.file_format, d.h_unit, d.m_unit, len(d.h)) == ("generic", "Oe", "emu", len(h))
    assert load_any(g)[0] == "VSM"


def test_rejects_non_vsm(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("Fe,Ni\n1,2\n")
    with pytest.raises(UnsupportedVsmFile):
        read_vsm(p)
    with pytest.raises(ValueError):
        load_any(p)


def test_golden_real_files():
    """tests/golden.csv의 실측 파일(samples/, 커밋 안 함)이 있으면 기대값과 대조, 없으면 건너뜀."""
    root = Path(__file__).resolve().parents[1]
    rows = list(csv.DictReader((root / "tests" / "golden.csv").open(encoding="utf-8")))
    found = [r for r in rows if (root / r["file"]).exists()]
    if not found:
        pytest.skip("실측 VSM 파일 없음(samples/)")
    for r in found:
        d = read_vsm(root / r["file"])
        res = analyze_loop(d.h, d.m)
        assert res["Hc"] == pytest.approx(float(r["Hc"]), rel=0.01, abs=0.1), r["file"]
        assert res["Ms"] == pytest.approx(float(r["Ms"]), rel=0.005), r["file"]
        if r.get("Mr"):
            assert res["Mr"] == pytest.approx(float(r["Mr"]), rel=0.01), r["file"]


def test_background_slope_removed():
    """합성 루프에 반자성 배경 −0.02·H를 더해도 기울기를 찾아 빼면 Ms·Hc가 원래대로."""
    h, m = loop(2.5)
    chi = high_field_slope(h, m - 0.02 * h)
    assert chi == pytest.approx(-0.02, abs=1e-9)
    r = analyze_loop(h, m - 0.02 * h, slope=chi)
    assert r["Ms"] == pytest.approx(50) and r["Hc"] == pytest.approx(2.5, abs=0.02)
    assert high_field_slope(h[:3], m[:3]) is None


def test_dmdh_peaks_at_switching_field():
    h, m = loop(2.5)
    d = dmdh(h, m)
    assert np.isnan(d).sum() <= 2  # 되돌이점만 끊김
    down = slice(0, h.size // 2)
    assert abs(h[down][np.nanargmax(d[down])]) <= 12.5 + 1  # 내려가는 가지 기울기 4 구간(−12.5~+7.5) 안
    assert np.nanmax(d) == pytest.approx(4)
