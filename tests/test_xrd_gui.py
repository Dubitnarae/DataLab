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


def test_edit_panel(qtbot, tmp_path):
    """M4 ① 편집 패널: 축 범위·눈금·로그·제목(수식)·범례·선 모양·표시 이름."""
    from datalab.gui.main_window import MainWindow
    from datalab.plot.figures import save

    w = MainWindow()
    qtbot.addWidget(w)
    for i in range(2):
        (tmp_path / f"d{i}").mkdir()
        w.open_paths([str(lakeshore(tmp_path / f"d{i}", {"hc": 2.5, "mr": 10, "ms": 50}, *loop(2.5)))])
    x, y = w.ax_w["x"], w.ax_w["y"]
    x["min"].setText("-20")
    x["max"].setText("20")
    x["step"].setValue(5)
    x["title"].setText(r"$\mu_0H$ (Oe)")
    y["log"].setChecked(True)  # 음수 M은 matplotlib가 가림 — 오류 없이 그려져야 함
    w.legend.setCurrentText("왼쪽 위")
    w.redraw()
    ax = w.fig.axes[0]
    assert ax.get_xlim() == (-20, 20) and ax.get_yscale() == "log"
    assert set(np.diff(ax.get_xticks())) == {5} and ax.get_xlabel() == r"$\mu_0H$ (Oe)"
    assert ax.get_legend()._loc == 2  # upper left
    w.list.item(0).setSelected(True)
    w.marker.setCurrentText("○")
    w.lw.setValue(3)
    w.list.item(0).setText("열처리 전")
    line = w.fig.axes[0].get_lines()[0]
    assert line.get_marker() == "o" and line.get_linewidth() == 3 and line.get_label() == "열처리 전"
    w.legend.setCurrentText("숨김")
    assert w.fig.axes[0].get_legend() is None
    y["title"].setText(r"$\nosuchcmd$")  # 수식 오류도 창이 죽지 않고 글자 그대로
    w.redraw()
    assert "수식 오류" in w.status.text()
    save(w.fig, tmp_path / "e.png")
    w.mode.setCurrentText("XRD")  # 종류를 바꾸면 축 설정을 비움
    assert x["min"].text() == "" and not y["log"].isChecked()


def test_panels_double_y(qtbot, tmp_path):
    """M4 ② 2·4 패널(시료 차례대로·지정 패널)과 Double-Y(오른쪽 Y축, 범례 하나로)."""
    from datalab.gui.main_window import MainWindow
    from datalab.plot.figures import save

    w = MainWindow()
    qtbot.addWidget(w)
    for i in range(3):
        (tmp_path / f"d{i}").mkdir()
        w.open_paths([str(lakeshore(tmp_path / f"d{i}", {"hc": 2.5, "mr": 10, "ms": 50}, *loop(2.5 + i)))])
    w.layout_box.setCurrentText("4패널(2×2)")
    panels = [a for a in w.fig.axes if a.get_xlabel()]
    assert len(panels) == 4 and [len(a.get_lines()) - 2 for a in panels] == [1, 1, 1, 0]  # -2: 원점 가로·세로 선
    w.ax_w["x"]["min"].setText("-50")
    w.redraw()
    assert all(a.get_xlim()[0] == -50 for a in w.fig.axes if a.get_xlabel())  # 편집 값은 모든 패널에
    w.layout_box.setCurrentText("세로 2패널")
    w.list.item(2).setSelected(True)
    w.panel.setCurrentIndex(1)  # 3번째 시료(차례대로면 패널 1) → 패널 1 지정
    w.right.setChecked(True)
    w.y2title.setText("M2")
    w.redraw()
    top = w.fig.axes[0]
    twin = [a for a in w.fig.axes if a.get_ylabel() == "M2"]
    assert len(twin) == 1 and len(twin[0].get_lines()) == 1
    assert twin[0].get_lines()[0].get_color() != top.get_lines()[0].get_color()  # 오른쪽 축도 색 이어서
    assert len(twin[0].get_legend().get_texts()) == 2 and top.get_legend() is None  # 범례 하나로 합침
    w.legend.setCurrentText("숨김")
    assert not any(a.get_legend() for a in w.fig.axes)
    save(w.fig, tmp_path / "p.png")
    w.mode.setCurrentText("XRD")  # XRD 빈 목록도 패널로 그려짐
    assert len(w.fig.axes) == 2


def test_template_roundtrip(qtbot, tmp_path):
    """M4 ③ 그래프 템플릿: JSON으로 저장 → 새 창에 불러오면 같은 그래프 모양."""
    import json

    from datalab.gui.main_window import MainWindow

    def window():
        w = MainWindow()
        qtbot.addWidget(w)
        for i in range(2):
            (tmp_path / f"d{i}").mkdir(exist_ok=True)
            w.open_paths([str(lakeshore(tmp_path / f"d{i}", {"hc": 2.5, "mr": 10, "ms": 50}, *loop(2.5 + i)))])
        return w

    a = window()
    a.style.setCurrentText("논문 1단")
    a.layout_box.setCurrentText("세로 2패널")
    a.h_unit.setCurrentText("kA/m")
    a.ax_w["x"]["min"].setText("-2")
    a.ax_w["y"]["title"].setText(r"$M$ (emu/g)")
    a.legend.setCurrentText("왼쪽 위")
    a.list.item(1).setSelected(True)
    a.marker.setCurrentText("□")
    a.lw.setValue(2)
    a.redraw()
    t = json.loads(json.dumps(a.template(), ensure_ascii=False))  # 파일 저장과 같은 변환
    b = window()
    b.apply_template(t)
    assert b.template() == t
    assert b.fig.axes[0].get_xlim()[0] == -2 and b.fig.axes[0].get_ylabel() == "$M$ (emu/g)"
    assert len([x for x in b.fig.axes if x.get_xlabel()]) == 2
    line = [x for x in b.fig.axes if x.get_xlabel()][1].get_lines()[0]
    assert line.get_marker() == "s" and line.get_linewidth() == 2
    with pytest.raises(ValueError):
        b.apply_template({"style": "PPT용"})  # 템플릿 표시 없는 JSON은 거부
    b.apply_template({"datalab_template": 1, "style": "없는 프리셋", "lines": [{"marker": "?"}]})  # 모르는 값은 건너뜀
    assert b.style.currentText() == "논문 1단" and "marker" not in b.items[0]["style"]
