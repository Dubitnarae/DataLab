"""화면 테마: 아이콘 경로·스타일시트 적용, matplotlib 도구 막대 아이콘이 지워지지 않는지(배경이 밝아야 함)."""

from pathlib import Path


def test_theme_applies(qtbot):
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
    from matplotlib.figure import Figure
    from PySide6.QtWidgets import QApplication

    from datalab.gui import theme
    from datalab.gui.main_window import MainWindow

    qss = theme.stylesheet()
    for name in ("check.svg", "chevron-down.svg", "chevron-up.svg"):
        assert Path(theme._icon(name)).is_file() and name in qss
    app = QApplication.instance()
    old = app.styleSheet()
    try:
        theme.apply(app)
        w = MainWindow()
        qtbot.addWidget(w)
        assert w.main_tabs.objectName() == "mainTabs"
        assert len(w.findChildren(type(w.main_tabs), "segTabs")) == 1
        tb = NavigationToolbar2QT(FigureCanvasQTAgg(Figure()), None)
        qtbot.addWidget(tb)
        assert tb.palette().color(tb.backgroundRole()).value() >= 128  # 어두우면 matplotlib 가 아이콘 색을 바꿔 안 보임
        assert "Noto Sans KR" not in theme.PLOT_RC["font.family"]  # matplotlib 에서 가장 얇게만 잡힘
    finally:
        app.setStyleSheet(old)
