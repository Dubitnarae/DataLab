"""XRD 연결(xrdcheck)과 GUI 기본 동작: 열기 → 그래프 → 결과 표 → 저장."""

import numpy as np
from PySide6.QtCore import Qt
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
    assert len(panels) == 4 and [len(a.get_lines()) for a in panels] == [3, 3, 3, 0]  # 원점 가로·세로 선 2개 포함
    assert not panels[3].axison  # 빈 패널은 축 숨김
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


def test_bw_and_font(qtbot, tmp_path):
    """M4 ④ 흑백 출판(검정 + 선 모양, 직접 고른 색은 유지)·글꼴 선택, 템플릿에도 담김."""
    import matplotlib

    from datalab.gui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    for i in range(3):
        (tmp_path / f"d{i}").mkdir()
        w.open_paths([str(lakeshore(tmp_path / f"d{i}", {"hc": 2.5, "mr": 10, "ms": 50}, *loop(2.5 + i)))])
    w.list.item(2).setSelected(True)
    w._set_line(color="#ff0000")
    w.bw.setChecked(True)
    w.font.setCurrentText("Times New Roman")
    lines = w.fig.axes[0].get_lines()[:3]
    hexes = [matplotlib.colors.to_hex(ln.get_color()) for ln in lines]  # "C0"은 그릴 때의 색 순환으로 풀림
    assert hexes == ["#000000", "#000000", "#ff0000"]
    assert [ln.get_linestyle() for ln in lines] == ["-", "--", ":"]
    ins = w.fig.axes[0].child_axes[0]  # 인셋도 같은 선 모양
    assert ins.get_lines()[1].get_linestyle() == "--"
    assert matplotlib.rcParams["font.family"][:2] == ["Times New Roman", "Arial"]
    assert matplotlib.rcParams["mathtext.fontset"] == "stix"
    t = w.template()
    assert t["bw"] is True and t["font"] == "Times New Roman"
    w.bw.setChecked(False)
    w.font.setCurrentText("Arial")
    w.apply_template(t)
    assert w.bw.isChecked() and w.font.currentText() == "Times New Roman"


def test_batch_export(qtbot, tmp_path):
    """M4 ⑤ 일괄 내보내기: 체크한 시료마다 한 장, 같은 스타일, 못 쓰는 글자·같은 이름 처리, 화면 그래프는 그대로."""
    from datalab.gui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    for i in range(3):
        (tmp_path / f"d{i}").mkdir()
        w.open_paths([str(lakeshore(tmp_path / f"d{i}", {"hc": 2.5, "mr": 10, "ms": 50}, *loop(2.5 + i)))])
    w.list.item(0).setText("A/B")
    w.list.item(1).setText("A_B")  # 정리하면 첫째와 같은 이름
    w.list.item(2).setCheckState(w.list.item(2).checkState().Unchecked)
    w.layout_box.setCurrentText("세로 2패널")
    w.list.item(0).setSelected(True)
    w.right.setChecked(True)  # 한 장짜리에서는 빠져야 함
    w.ax_w["x"]["min"].setText("-30")
    w.redraw()
    screen = w.fig
    out = tmp_path / "out"
    out.mkdir()
    paths = w.batch_export(out, ".png")
    assert [p.name for p in paths] == ["A_B.png", "A_B_2.png"]
    assert all(p.stat().st_size > 1000 for p in paths)
    assert w.fig is screen  # 화면 그래프는 바뀌지 않음
    fig, _ = w._figure([{**w.checked()[0], "style": {}}], "한 그래프")
    assert len([a for a in fig.axes if a.get_xlabel()]) == 1 and fig.axes[0].get_xlim()[0] == -30


def test_vsm_background_and_dmdh(qtbot, tmp_path):
    """M4 ⑥: 배경 기울기 빼기 → 결과 표에 χ·보정 전 값, 세로축 dM/dH → 축 제목·인셋 없음."""
    from datalab.gui.main_window import MainWindow

    h, m = loop(2.5)
    w = MainWindow()
    qtbot.addWidget(w)
    w.open_paths([str(lakeshore(tmp_path, {"hc": 2.5, "mr": 10, "ms": 50}, h, m - 0.02 * h))])
    w.bg.setChecked(True)
    keys = [w.table.verticalHeaderItem(i).text() for i in range(w.table.rowCount())]
    vals = {k: w.table.item(i, 0).text() for i, k in enumerate(keys)}
    assert float(vals["배경 기울기 χ (emu/g/Oe)"]) == pytest.approx(-0.02) and float(vals["Ms (emu/g)"]) == pytest.approx(50)
    w.vsm_y.setCurrentText("dM/dH")
    ax = w.fig.axes[0]
    assert ax.get_ylabel() == "dM/dH (emu/g/Oe)" and len(w.fig.axes) == 1  # 인셋 없음
    assert w.template()["vsm_y"] == "dM/dH" and "bg" not in w.template()
    w.smooth.setValue(9)
    assert w.template()["smooth"] == 9


def test_known_limits_fixed(qtbot, tmp_path, recwarn):
    """수식+한글 축 제목은 맑은 고딕(□ 없음), 빈 패널은 축 숨김, 흑백 선 모양 7종·인셋도 같은 파선."""
    from datalab.gui.main_window import MainWindow
    from datalab.plot import figures

    w = MainWindow()
    qtbot.addWidget(w)
    for i in range(5):
        (tmp_path / f"d{i}").mkdir()
        w.open_paths([str(lakeshore(tmp_path / f"d{i}", {"hc": 2.5, "mr": 10, "ms": 50}, *loop(2.5 + i)))])
    w.bw.setChecked(True)
    lines = w.fig.axes[0].get_lines()[:5]
    assert [ln.get_linestyle() for ln in lines[:4]] == ["-", "--", ":", "-."] and len(figures.BW_LS) == 7
    ins = w.fig.axes[0].child_axes[0]
    assert ins.get_lines()[4]._unscaled_dash_pattern == lines[4]._unscaled_dash_pattern
    w.ax_w["x"]["title"].setText(r"자장 $\mu_0H$ (T)")
    w.redraw()
    assert w.fig.axes[0].xaxis.label.get_fontfamily() == ["Malgun Gothic"]
    w.fig.canvas.draw()
    assert not [x for x in recwarn if "glyph" in str(x.message)]
    for i in range(1, 5):
        w.list.item(i).setCheckState(Qt.CheckState.Unchecked)
    w.layout_box.setCurrentText("4패널(2×2)")
    panels = [a for a in w.fig.axes if a.get_subplotspec()]
    assert [a.axison for a in panels] == [True, False, False, False]


def test_db_save_dedup(qtbot, tmp_path, xrd_file):
    """같은 원본을 두 번 저장해도 측정은 하나, 원본 사본도 하나."""
    import sqlite3

    from datalab.gui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.db_root = tmp_path / "db"
    w.open_paths([str(lakeshore(tmp_path, {"hc": 2.5, "mr": 10, "ms": 50}, *loop(2.5)))])
    assert w.save_to_db() == (1, 0)
    assert w.save_to_db() == (0, 1)
    w.open_paths([str(xrd_file)])
    assert w.save_to_db() == (1, 0)
    con = sqlite3.connect(w.db_root / "datalab.sqlite")
    assert con.execute("SELECT COUNT(*) FROM measurements").fetchone()[0] == 2
    hc = con.execute("SELECT value, unit, analysis_version FROM results WHERE key = 'Hc'").fetchone()
    assert hc[0] == pytest.approx(2.5) and hc[1:] == ("Oe", "vsm-1")
    assert con.execute("SELECT COUNT(*) FROM results r JOIN measurements m ON m.id = r.measurement_id"
                       " WHERE m.kind = 'XRD' AND r.key = '판정'").fetchone()[0] == 1
    con.close()
    assert len(list((w.db_root / "originals").iterdir())) == 2


def test_db_dialog_tag_and_reopen(qtbot, tmp_path, xrd_file):
    """DB 목록에서 조성·태그를 고치면 저장되고, 원본 사본을 시료 이름으로 다시 연다."""
    from datalab import db
    from datalab.gui.db_dialog import SAMPLE_COLS, DbDialog
    from datalab.gui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.db_root = tmp_path / "db"
    w.open_paths([str(xrd_file)])
    w.list.item(0).setText("합금A")
    w.save_to_db()
    w.items.clear()
    w._fill_list()

    d = DbDialog(w, w.db_root)
    qtbot.addWidget(d)
    assert d.samples.rowCount() == 1 and d.meas.rowCount() == 1
    col = {k: i for i, (k, _) in enumerate(SAMPLE_COLS)}
    d.samples.item(0, col["composition"]).setText("Fe78Si9B13")
    d.samples.item(0, col["tags"]).setText("리본, 열처리 ,리본")
    assert d.open_selected() == 1
    assert [it["name"] for it in w.items] == ["합금A"] and w.mode.currentText() == "XRD"
    d.reject()

    s = db.Store(w.db_root)
    row = s.samples()[0]
    assert (row["composition"], row["tags"], row["n"]) == ("Fe78Si9B13", "리본, 열처리", 1)
    with pytest.raises(ValueError):
        s.update_sample(1, "name; DROP TABLE samples", "x")
    s.close()


def test_db_search_filter(qtbot, tmp_path, xrd_file):
    """검색어(단어 모두 포함)·종류로 시료 목록을 거른다."""
    from datalab import db
    from datalab.gui.db_dialog import DbDialog
    from datalab.gui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.db_root = tmp_path / "db"
    w.open_paths([str(lakeshore(tmp_path, {"hc": 2.5, "mr": 10, "ms": 50}, *loop(2.5)))])
    w.list.item(0).setText("리본B")
    w.save_to_db()
    w.open_paths([str(xrd_file)])
    w.list.item(0).setText("합금A")
    w.save_to_db()
    s = db.Store(w.db_root)
    sid = {r["name"]: r["id"] for r in s.samples()}
    s.update_sample(sid["합금A"], "composition", "Fe78Si9B13")
    s.update_sample(sid["합금A"], "tags", "열처리")
    names = lambda *a: [r["name"] for r in s.samples(*a)]
    assert names() == ["리본B", "합금A"]
    assert names("fe78 열처리") == ["합금A"]
    assert names("fe78 없음") == []
    assert names(xrd_file.name[:4].upper()) == ["합금A"]  # 원본 파일 이름도 찾음
    assert names("", "VSM") == ["리본B"] and names("", "XRD") == ["합금A"]
    s.close()

    d = DbDialog(w, w.db_root)
    qtbot.addWidget(d)
    d.kind.setCurrentText("XRD")
    assert d.samples.rowCount() == 1 and d.samples.item(0, 0).text() == "합금A"
    d.search.setText("없는말")
    assert d.samples.rowCount() == 0 and d.meas.rowCount() == 0
    d.reject()


def test_db_compare_xlsx(qtbot, tmp_path, xrd_file):
    """비교표: 걸러진 시료의 측정 한 줄씩, 결과 열 'key (단위)', 숫자 정렬, Excel 저장."""
    from openpyxl import load_workbook

    from datalab.gui.db_dialog import DbDialog
    from datalab.gui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.db_root = tmp_path / "db"
    for name, hc in (("리본B", 2.5), ("리본A", 7.0)):
        sub = tmp_path / name
        sub.mkdir()
        w.open_paths([str(lakeshore(sub, {"hc": hc, "mr": 10, "ms": 50}, *loop(hc)))])
        w.list.item(w.list.count() - 1).setText(name)
        w.save_to_db()
    w.open_paths([str(xrd_file)])
    w.list.item(0).setText("합금A")
    w.save_to_db()

    d = DbDialog(w, w.db_root)
    qtbot.addWidget(d)
    d.kind.setCurrentText("VSM")
    c = d.compare()
    qtbot.addWidget(c)
    assert c.table.rowCount() == 2 and "Hc (Oe)" in c.heads and "판정" not in c.heads
    col = c.heads.index("Hc (Oe)")
    c.table.sortItems(col, Qt.SortOrder.DescendingOrder)
    assert c.table.item(0, 0).text() == "리본A"  # 7.0 > 2.5, 글자 순이 아니라 숫자 순
    out = tmp_path / "cmp.xlsx"
    assert c.save_xlsx(str(out))
    ws = load_workbook(out).active
    assert [x.value for x in ws[1]] == c.heads
    assert ws.cell(2, 1).value == "리본A" and ws.cell(2, col + 1).value == pytest.approx(7.0)

    d.kind.setCurrentText("전체")
    c2 = d.compare()
    qtbot.addWidget(c2)
    assert c2.table.rowCount() == 3 and "판정" in c2.heads and "Hc (Oe)" in c2.heads
    d.reject()
