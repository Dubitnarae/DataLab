"""Origin 대비 추가 기능(v0.2.0): 데이터 처리·피팅 계산, 그래프 배치·오차 막대·주석, 새 탭."""

import numpy as np
import pytest

from datalab.analysis import fit, process
from tests.test_vsm import lakeshore, loop


@pytest.fixture(autouse=True)
def no_dialogs(monkeypatch):
    """경고 창은 모달이라 시험이 멈춤 — 띄운 내용만 기록."""
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[1:3]))
    return shown


# ------------------------------------------------------------------ 계산
def test_process_apply_range_drop_ref_smooth():
    h, m = loop(2.5)
    inside = (h >= -50) & (h <= 50)
    x, y, e = process.apply(h, m, np.ones(h.size), {"xmin": -50, "xmax": 50, "drop": [int(np.flatnonzero(inside)[0])]})
    assert x.min() >= -50 and x.max() <= 50 and e.size == x.size == inside.sum() - 1
    # 기준 = 같은 루프 → 가지별로 빼면 0(전 구간 보간이면 이력 때문에 0이 안 됨)
    _, y2, _ = process.apply(h, m, None, {}, (h, m))
    assert np.abs(y2).max() < 1e-9
    _, y3, _ = process.apply(h, m, None, {"xmin": 0, "common_only": True}, (h[h > -20], m[h > -20]))
    assert y3.size == (h >= 0).sum()
    noisy = m + np.random.default_rng(0).normal(0, 1, m.size)
    for kind in ("aav", "sg"):
        _, ys, _ = process.apply(h, noisy, None, {"smooth": kind, "smooth_n": 9, "smooth_order": 2})
        assert np.abs(ys - m).mean() < np.abs(noisy - m).mean()
    assert "구간" in process.describe({"xmin": 1}) and process.describe({}) == "없음"


def test_find_spikes_integrate_interp():
    x = np.linspace(20, 80, 600)
    y = 100 + 5 * np.sin(x)
    y[[50, 300]] += 500
    assert process.find_spikes(y) == [50, 300]
    r = process.integrate(x, fit.gauss(x, 50, 2, 10))
    assert r["area"] == pytest.approx(10, rel=1e-4) and r["fwhm"] == pytest.approx(2, rel=5e-3)
    assert r["x_at_max"] == pytest.approx(50, abs=0.1)
    h, m = loop(2.5)
    loss = process.integrate(h, m)["area"]  # 루프 둘러싼 면적 = 폭 2Hc × 높이 2Ms
    assert abs(loss) == pytest.approx(2 * 2.5 * 100, rel=0.05)
    br = process.interp_at(h, m, [0.0])
    assert set(br) == {"내려가는 가지", "올라가는 가지"} and abs(br["내려가는 가지"][0]) == pytest.approx(10)
    assert process.interp_at(x, x * 2, [30.5])["Y"][0] == pytest.approx(61)


@pytest.mark.parametrize("kind", list(fit.PEAKS))
def test_peak_fit_recovers(kind):
    f, shape = fit.PEAKS[kind]
    x = np.linspace(40, 50, 800)
    args = (43.0, 0.4, 20.0) + ((shape[1] + 0.3,) if shape else ())
    args2 = (46.0, 0.6, 12.0) + ((shape[1] + 0.3,) if shape else ())
    y = 3 + 0.1 * (x - 40) + f(x, *args) + f(x, *args2) + np.random.default_rng(1).normal(0, 0.05, x.size)
    r = fit.fit_peaks(x, y, kind, n=2, baseline="직선")
    p1, p2 = r["peaks"]
    assert p1["xc"] == pytest.approx(43, abs=0.01) and p2["xc"] == pytest.approx(46, abs=0.01)
    assert p1["w"] == pytest.approx(0.4, rel=0.03) and p1["area"] == pytest.approx(20, rel=0.03)
    assert r["r2"] > 0.99


def test_langevin_and_saturation():
    h = np.r_[np.linspace(2e4, -2e4, 300), np.linspace(-2e4, 2e4, 300)]
    r = fit.fit_langevin(h, 40 * fit.langevin(h / 500) + 2e-4 * h)
    assert r["Ms"] == pytest.approx(40, rel=1e-3) and r["a"] == pytest.approx(500, rel=1e-3)
    m = np.sign(h) * 40 * (1 - 300 / np.maximum(abs(h), 1)) + 1e-4 * h
    s = fit.fit_saturation(h, m, 0.3, ("a", "chi"))
    assert s["b"] == 0 and s["terms"] == ["a", "chi"]
    assert s["Ms"] == pytest.approx(40, rel=1e-3) and s["a"] == pytest.approx(300, rel=1e-2)
    assert np.isnan(s["curve"](np.array([0.0])))[0]  # 맞춘 구간 밖은 그리지 않음
    with pytest.raises(ValueError):
        fit.fit_saturation(h[:20], m[:20], 0.99)


# ------------------------------------------------------------------ 그래프
def test_figures_stack_errbar_offset_notes(tmp_path):
    from datalab.plot import figures

    figures.apply_style("논문 1단")
    x = np.linspace(20, 80, 300)
    items = [(f"s{k}", x, 100 + 50 * np.exp(-((x - 40 - k) / 2) ** 2), {"err": np.full(x.size, 3.0)}) for k in range(3)]
    fig = figures.new_figure("논문 1단")
    panels = figures.draw_xrd(fig, items, 0.1, True, figures.STACK)
    assert len(panels) == 3 and panels[0].get_xlabel() == "" and panels[-1].get_xlabel() == "2θ (°)"
    assert all(p.get_legend() for p in panels) and fig.get_supylabel()
    assert any(c.__class__.__name__ == "ErrorbarContainer" for c in panels[0].containers)
    fig = figures.new_figure("논문 1단")
    panels = figures.draw_xrd(fig, [(n, a, b, {}) for n, a, b, _ in items], 0.1, True, "한 그래프", figures.OFFSET_MODES[1])
    lows = [ln.get_ydata().min() for ln in panels[0].get_lines()]
    tops = [ln.get_ydata().max() for ln in panels[0].get_lines()]
    assert lows[1] == pytest.approx(tops[0] + 0.1) and lows[2] == pytest.approx(tops[1] + 0.1)  # 누적: 겹치지 않음
    figures.apply_axes(panels[0], {"legend": "오른쪽 위", "legend_rev": True})
    assert [t.get_text() for t in panels[0].get_legend().get_texts()] == ["s2", "s1", "s0"]
    figures.annotate(panels, [{"text": "(110) 피크 $\\alpha$", "x": 40, "y": 1, "tx": 60, "ty": 2, "panel": 5}])
    ann = panels[0].texts[-1]
    assert ann.arrow_patch is not None and ann.get_fontfamily() == ["Malgun Gothic"]
    p = figures.save(fig, tmp_path / "a.eps")
    assert p.read_bytes()[:4] == b"%!PS"
    fig = figures.new_figure("논문 1단")
    assert len(figures.draw_xrd(fig, items[:1], layout="9패널(3×3)")) == 9


# ------------------------------------------------------------------ 화면
def _open3(w, tmp_path):
    for i in range(3):
        (tmp_path / f"d{i}").mkdir()
        w.open_paths([str(lakeshore(tmp_path / f"d{i}", {"hc": 2.5, "mr": 10, "ms": 50}, *loop(2.5 + i)))])


def test_tabs_exist_and_panel_axes_order_template(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    from datalab.gui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    assert [w.main_tabs.tabText(i) for i in range(w.main_tabs.count())] == \
        ["그래프", "데이터 처리", "피크 피팅", "자기 포화 피팅", "워크시트"]
    _open3(w, tmp_path)
    w.layout_box.setCurrentText("세로 2패널")
    w.ax_w["x"]["min"].setText("-40")
    w.redraw()
    w.ax_target.setCurrentIndex(2)  # 패널 2 따로
    assert w.ax_w["x"]["min"].text() == "-40"  # 보기만 하면 모든 패널 값
    w.ax_w["x"]["min"].setText("-10")
    w.redraw()
    panels = [a for a in w.fig.axes if a.get_xlabel()]
    assert panels[0].get_xlim()[0] == -40 and panels[1].get_xlim()[0] == -10
    w.add_note("Hc", 2.5, 0, 20, 20, 1)
    t = w.template()
    assert t["panel_axes"]["2"]["xmin"] == -10 and t["axes"]["x"]["min"] == -40 and t["notes"][0]["text"] == "Hc"
    # 순서 바꾸기: 체크 해제 상태 유지, 그리는 순서 바뀜
    w.list.item(2).setCheckState(Qt.CheckState.Unchecked)
    first = w.list.item(0).text()
    w.list.setCurrentRow(0)
    w.move_selected(1)
    assert w.list.item(1).text() == first and w.list.item(2).checkState() == Qt.CheckState.Unchecked
    w._clear_target()  # 지금 대상(패널 2) 따로 설정 지우기
    w.mode.setCurrentText("XRD")
    w.mode.setCurrentText("VSM")
    assert w.notes == [] and w.axes_for(2)["xmin"] is None
    w.apply_template(t)
    assert w.axes_for(2)["xmin"] == -10 and w.notes and w.ax_w["x"]["min"].text() == "-40"


def test_process_tab_changes_results(qtbot, tmp_path):
    from datalab.gui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    h, m = loop(2.5)
    m = m.copy()
    m[150] += 400  # 튀는 점
    w.open_paths([str(lakeshore(tmp_path, {"hc": 2.5, "mr": 10, "ms": 50}, h, m))])

    def ms():
        return float(next(w.table.item(i, 0).text() for i in range(w.table.rowCount())
                          if w.table.verticalHeaderItem(i).text() == "Ms (emu/g)"))
    assert ms() > 100  # 튀는 점 때문에 Ms가 부풀어 있음
    t = w.process_tab
    w.main_tabs.setCurrentWidget(t)
    t.find_spikes()
    assert 150 in t._cands
    t.drop_checked()
    t.apply()
    assert ms() == pytest.approx(50)
    rows = {w.table.verticalHeaderItem(i).text() for i in range(w.table.rowCount())}
    assert "데이터 처리" in rows
    t.ilo.setText("-200")
    t.ihi.setText("200")
    t.integrate()
    assert t.table.rowCount() == 5
    t.ixs.setText("0, 10")
    t.interpolate()
    assert t.table.columnCount() == 3  # X + 가지 둘
    t.clear()
    assert ms() > 100


def test_fit_and_sheet_tabs(qtbot, tmp_path, no_dialogs):
    import sqlite3

    from datalab.gui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.db_root = tmp_path / "db"
    h = np.r_[np.linspace(1e4, -1e4, 300), np.linspace(-1e4, 1e4, 300)]
    w.open_paths([str(lakeshore(tmp_path, {"hc": 0, "mr": 0, "ms": 30}, h, 30 * fit.langevin(h / 400)))])
    s = w.sat_tab
    w.main_tabs.setCurrentWidget(s)
    r = s.run()
    assert r["Ms"] == pytest.approx(30, rel=1e-3) and s.table.rowCount() == 5
    s.model.setCurrentIndex(1)
    assert s.run() is not None
    m2 = np.sign(h) * 30 * (1 - 4e5 / h ** 2)  # b/H² 만 있는 고자장
    assert fit.fit_saturation(h, m2, 0.5)["Ms"] == pytest.approx(30, rel=1e-6)
    p = w.peak_tab
    w.main_tabs.setCurrentWidget(p)
    p.lo.setText("-3000")
    p.hi.setText("3000")
    p.kind.setCurrentText("Gauss")
    assert p.run() is not None and p.table.rowCount() == 2  # 피크 1 + R²
    sh = w.sheet_tab
    w.main_tabs.setCurrentWidget(sh)
    assert sh.table.rowCount() == 600
    sh.save_csv(str(tmp_path / "o.csv"))
    assert (tmp_path / "o.csv").read_text(encoding="utf-8-sig").splitlines()[0].startswith("H (Oe),M (emu/g)")
    sh.formula.setText("y * 2")
    new = sh.make_sample()
    assert new["derived"] and np.allclose(new["data"].m, 60 * fit.langevin(h / 400), atol=1e-6)
    assert len(w.items) == 2
    sh.formula.setText("__import__('os')")
    assert sh.make_sample() is None  # 내장 함수 없음
    assert no_dialogs and no_dialogs[-1][0] == "식 오류"
    assert w.save_to_db() == (1, 0)  # 만든 시료는 DB에 안 넣음
    con = sqlite3.connect(w.db_root / "datalab.sqlite")
    assert con.execute("SELECT COUNT(*) FROM measurements").fetchone()[0] == 1


def test_xrd_process_reanalyzes_and_errbars(qtbot, tmp_path):
    from datalab.gui.main_window import MainWindow

    rng = np.random.default_rng(0)
    x = np.arange(20, 80, 0.02)
    y = 200 + 1500 * np.exp(-((x - 44.5) / 4) ** 2) + 3000 * np.exp(-((x - 65.0) / 0.15) ** 2)
    f = tmp_path / "s1.xy"
    f.write_text("\n".join(f"{a:.3f} {b:.1f}" for a, b in zip(x, rng.poisson(y))))
    w = MainWindow()
    qtbot.addWidget(w)
    w.open_paths([str(f)])
    w.err.setChecked(True)
    assert any(c.__class__.__name__ == "ErrorbarContainer" for c in w.fig.axes[0].containers)
    t = w.process_tab
    w.main_tabs.setCurrentWidget(t)
    t.xmin.setText("30")
    t.xmax.setText("70")
    t.apply()
    assert w.items[0].get("xrd_proc") is not None and w.fig.axes[0].get_lines()[0].get_xdata().min() >= 30
