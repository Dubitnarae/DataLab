"""XRD 연결(xrdcheck)과 GUI 기본 동작: 열기 → 그래프 → 결과 표 → 저장."""

import numpy as np
import pytest

from datalab.analysis import xrd as xrd_an
from datalab.io import load_any
from tests.test_vsm import lakeshore, loop


@pytest.fixture
def xrd_file(tmp_path):
    rng = np.random.default_rng(0)
    x = np.arange(20, 80, 0.02)
    y = 200 + 1500 * np.exp(-((x - 44.5) / 4) ** 2) + 3000 * np.exp(-((x - 65.0) / 0.15) ** 2)
    p = tmp_path / "s1.xy"
    p.write_text("\n".join(f"{a:.3f} {b:.1f}" for a, b in zip(x, rng.poisson(y))))
    return p


def test_xrd_through_xrdcheck(xrd_file):
    kind, pat = load_any(xrd_file)
    assert kind == "XRD"
    res = xrd_an.analyze(pat)
    s = xrd_an.summary(res)
    assert res.verdict.value in s.values()  # 판정은 xrdcheck가 낸 그대로
    assert res.peaks  # 65° 결정 피크


def test_gui_open_plot_export(qtbot, tmp_path, xrd_file):
    from datalab.gui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.open_paths([str(lakeshore(tmp_path, {"hc": 2.5, "mr": 10, "ms": 50}, *loop(2.5)))])
    assert w.mode.currentText() == "VSM" and w.list.count() == 1
    keys = [w.table.verticalHeaderItem(i).text() for i in range(w.table.rowCount())]
    vals = {k: w.table.item(i, 0).text() for i, k in enumerate(keys)}
    assert vals["Hc (Oe)"] == "2.5" and vals["장비 값 대조"] == "일치"
    w.h_unit.setCurrentText("kA/m")
    assert w.table.verticalHeaderItem(1).text() == "Hc (kA/m)"
    for style in ("PPT용", "논문 1단", "논문 2단"):
        w.style.setCurrentText(style)
        for ext in (".png", ".svg", ".pdf"):
            out = tmp_path / f"g_{style}{ext}"
            from datalab.plot.figures import save
            save(w.fig, out)
            assert out.stat().st_size > 1000
    w.open_paths([str(xrd_file)])
    assert w.mode.currentText() == "XRD" and w.list.count() == 1 and w.table.rowCount() > 0
    w.list.selectAll()
    w.remove_selected()
    assert w.list.count() == 0 and len(w.items) == 1  # VSM 항목은 남는다
