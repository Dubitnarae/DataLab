"""화면 테마: 토스 앱 같은 느낌(연회색 바탕 위 흰 카드, 둥근 모서리, 파란 강조색 하나, 테두리 대신 면 색).

프로그램 화면에만 쓴다. 저장·복사되는 그래프(plot/figures.py)는 논문·PPT 규격이라 건드리지 않는다.
색 이름은 회색 단계(GREY_50 ~ GREY_900)와 파랑(BLUE) — 위젯마다 색을 따로 정하지 말고 여기 값을 쓴다.
"""

from __future__ import annotations

from importlib import resources

from cycler import cycler

from PySide6.QtCore import Qt
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from PySide6.QtGui import QColor, QFont, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QFormLayout, QWidget

BLUE, BLUE_HOVER, BLUE_PRESSED, BLUE_50 = "#3182F6", "#2272EB", "#1B64DA", "#E8F3FF"
GREY_50, GREY_100, GREY_200, GREY_300 = "#F9FAFB", "#F2F4F6", "#E5E8EB", "#D1D6DB"
GREY_400, GREY_500, GREY_600, GREY_700 = "#B0B8C1", "#8B95A1", "#6B7684", "#4E5968"
GREY_800, GREY_900, RED = "#333D4B", "#191F28", "#F04452"
FONTS = ["Pretendard", "Noto Sans KR", "Malgun Gothic"]  # 없는 글꼴은 다음 것으로(회사 PC는 보통 맑은 고딕)


def _mpl_fonts() -> list[str]:
    """matplotlib 은 없는 글꼴마다 경고를 찍으므로 설치된 것만. Noto Sans KR(가변 글꼴)은 matplotlib 에서
    가장 얇은 굵기로만 잡혀 빼고 맑은 고딕을 쓴다."""
    from matplotlib import font_manager

    have = {f.name for f in font_manager.fontManager.ttflist}
    return [f for f in ("Pretendard", "Malgun Gothic") if f in have] + ["DejaVu Sans"]


FONT_PT = 10

# 탭 미리보기 그림(matplotlib)도 같은 색으로 — 저장용 그래프와는 따로
PLOT_RC = {"font.family": _mpl_fonts(), "font.size": 9, "axes.unicode_minus": False,
           "lines.linewidth": 1.4, "xtick.direction": "out", "ytick.direction": "out",
           "xtick.top": False, "ytick.right": False, "xtick.minor.visible": False, "ytick.minor.visible": False,
           "axes.edgecolor": GREY_300, "axes.labelcolor": GREY_700, "text.color": GREY_800,
           "xtick.color": GREY_600, "ytick.color": GREY_600, "axes.titleweight": "bold", "axes.titlesize": 10,
           "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GREY_100,
           "legend.frameon": False,
           "axes.prop_cycle": cycler(color=[BLUE, "#F04452", "#03B26C", "#FE9800", "#A234C7",
                                                                    "#18A5A5", GREY_600])}


def _icon(name: str) -> str:
    p = resources.files("datalab").joinpath(f"data/{name}")
    return str(p).replace("\\", "/")  # QSS url() 은 / 경로


def stylesheet() -> str:
    check, down, up = _icon("check.svg"), _icon("chevron-down.svg"), _icon("chevron-up.svg")
    return f"""
* {{ color: {GREY_800}; outline: 0; }}
QMainWindow {{ background: {GREY_100}; }}
QDialog {{ background: white; }}  /* 창 위 시트 — 회색 버튼이 바탕에 묻히지 않게 */
QToolTip {{ background: {GREY_800}; color: white; border: none; border-radius: 6px; padding: 6px 8px; }}

/* 카드: 흰 면 + 둥근 모서리, 테두리 없음 */
#card {{ background: white; border-radius: 16px; }}
QGroupBox {{ background: white; border: none; border-radius: 16px; margin-top: 30px; padding: 12px 14px 14px 14px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 6px; top: 6px;
                    color: {GREY_900}; font-weight: bold; }}
QLabel#section {{ color: {GREY_900}; font-weight: bold; padding-top: 10px; }}
QLabel#hint {{ color: {GREY_600}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QSplitter::handle {{ background: transparent; }}

/* 메뉴·상태 줄 */
QMenuBar {{ background: {GREY_100}; padding: 4px 8px; }}
QMenuBar::item {{ padding: 6px 10px; border-radius: 8px; background: transparent; }}
QMenuBar::item:selected {{ background: {GREY_200}; }}
QMenu {{ background: white; border: 1px solid {GREY_200}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 8px 28px 8px 14px; border-radius: 8px; }}
QMenu::item:selected {{ background: {GREY_100}; color: {GREY_900}; }}
QMenu::separator {{ height: 1px; background: {GREY_100}; margin: 4px 8px; }}
QStatusBar {{ background: {GREY_100}; }}
QStatusBar QLabel {{ color: {GREY_600}; padding: 2px 8px; }}

/* 맨 위 탭: 글자 탭 + 고른 탭만 진하게·파란 밑줄 */
QTabWidget::pane {{ border: none; background: transparent; }}
QTabWidget#mainTabs > QTabBar {{ background: transparent; }}
QTabWidget#mainTabs > QTabBar::tab {{ background: transparent; color: {GREY_500}; font-weight: bold;
    padding: 10px 4px 9px 4px; margin: 0 14px 0 4px; border: none; border-bottom: 3px solid transparent; }}
QTabWidget#mainTabs > QTabBar::tab:selected {{ color: {GREY_900}; border-bottom: 3px solid {GREY_900}; }}
QTabWidget#mainTabs > QTabBar::tab:hover:!selected {{ color: {GREY_700}; }}
/* 안쪽 탭(옵션|그래프 편집): 회색 바탕 위 흰 알약(세그먼트) */
QTabWidget#segTabs > QTabBar {{ background: transparent; }}
QTabWidget#segTabs > QTabBar::tab {{ background: {GREY_100}; color: {GREY_600}; padding: 7px 18px; border: none;
    margin: 0; }}
QTabWidget#segTabs > QTabBar::tab:first {{ border-top-left-radius: 10px; border-bottom-left-radius: 10px; }}
QTabWidget#segTabs > QTabBar::tab:last {{ border-top-right-radius: 10px; border-bottom-right-radius: 10px; }}
QTabWidget#segTabs > QTabBar::tab:selected {{ background: {GREY_800}; color: white; font-weight: bold; }}

/* 버튼: 기본은 연회색 면, 핵심 동작만 파랑(primary) */
QPushButton {{ background: {GREY_100}; color: {GREY_800}; border: none; border-radius: 8px;
    padding: 7px 14px; min-height: 18px; }}
QPushButton:hover {{ background: {GREY_200}; }}
QPushButton:pressed {{ background: {GREY_300}; }}
QPushButton:disabled {{ color: {GREY_400}; background: {GREY_50}; }}
QPushButton[primary="true"] {{ background: {BLUE}; color: white; font-weight: bold; padding: 9px 16px; }}
QPushButton[primary="true"]:hover {{ background: {BLUE_HOVER}; }}
QPushButton[primary="true"]:pressed {{ background: {BLUE_PRESSED}; }}
QDialogButtonBox QPushButton {{ min-width: 72px; }}

/* 입력 칸: 회색 면, 누르면 파란 테두리 */
QLineEdit, QComboBox, QAbstractSpinBox {{ background: {GREY_100}; border: 1.5px solid transparent;
    border-radius: 8px; padding: 5px 8px; min-height: 18px; selection-background-color: {BLUE};
    selection-color: white; }}
QLineEdit:hover, QComboBox:hover, QAbstractSpinBox:hover {{ background: {GREY_200}; }}
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus {{ border: 1.5px solid {BLUE}; background: white; }}
QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled {{ color: {GREY_400}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({down}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: white; border: 1px solid {GREY_200}; border-radius: 10px; padding: 4px;
    selection-background-color: {BLUE_50}; selection-color: {BLUE}; outline: 0; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ border: none; width: 18px; background: transparent; }}
QAbstractSpinBox::up-arrow {{ image: url({up}); width: 10px; height: 10px; }}
QAbstractSpinBox::down-arrow {{ image: url({down}); width: 10px; height: 10px; }}

/* 체크 상자: 둥근 사각, 켜면 파랑 + 흰 체크 */
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator, QListView::indicator {{ width: 18px; height: 18px; border-radius: 5px;
    border: 1.5px solid {GREY_300}; background: white; }}
QCheckBox::indicator:hover, QListView::indicator:hover {{ border-color: {BLUE}; }}
QCheckBox::indicator:checked, QListView::indicator:checked {{ background: {BLUE}; border-color: {BLUE};
    image: url({check}); }}

/* 목록·표 */
QListWidget, QListView {{ background: transparent; border: none; }}
QListWidget::item {{ padding: 7px 6px; border-radius: 8px; margin: 1px 0; }}
QListWidget::item:hover {{ background: {GREY_50}; }}
QListWidget::item:selected {{ background: {BLUE_50}; color: {BLUE}; }}
QTableWidget, QTableView {{ background: white; border: none; gridline-color: {GREY_100};
    selection-background-color: {BLUE_50}; selection-color: {GREY_900}; alternate-background-color: {GREY_50}; }}
QHeaderView {{ background: white; border: none; }}
QHeaderView::section {{ background: white; color: {GREY_500}; border: none; border-bottom: 1px solid {GREY_200};
    padding: 6px 8px; font-weight: bold; }}
QTableCornerButton::section {{ background: white; border: none; }}

/* 스크롤바: 가늘고 둥글게 */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {GREY_300}; border-radius: 3px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {GREY_400}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none;
    border: none; width: 0; height: 0; }}

/* matplotlib 도구 막대 */
QToolBar {{ background: white; border: none; spacing: 2px; }}  /* transparent 면 matplotlib 가 어두운 배경으로 보고 아이콘을 지움 */
QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 5px; }}
QToolButton:hover {{ background: {GREY_100}; }}
QToolButton:checked {{ background: {BLUE_50}; }}

/* 진행 창·메시지 */
QProgressBar {{ background: {GREY_100}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {BLUE}; border-radius: 4px; }}
QMessageBox {{ background: white; }}
QMessageBox QLabel {{ color: {GREY_800}; }}
"""


def apply(app: QApplication) -> None:
    """앱 전체에 글꼴·색·스타일시트를 건다(창을 만들기 전에 부를 것)."""
    font = QFont()
    font.setFamilies(FONTS)
    font.setPointSize(FONT_PT)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    pal = app.palette()
    for role, c in ((QPalette.ColorRole.Window, GREY_100), (QPalette.ColorRole.Base, "#FFFFFF"),
                    (QPalette.ColorRole.AlternateBase, GREY_50), (QPalette.ColorRole.Text, GREY_800),
                    (QPalette.ColorRole.WindowText, GREY_800), (QPalette.ColorRole.Button, GREY_100),
                    (QPalette.ColorRole.ButtonText, GREY_800), (QPalette.ColorRole.Highlight, BLUE),
                    (QPalette.ColorRole.HighlightedText, "#FFFFFF"),
                    (QPalette.ColorRole.PlaceholderText, GREY_400)):
        pal.setColor(role, QColor(c))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet())


# 그래프 도구 막대 아이콘: 24칸 격자 선 그림(둥근 끝), matplotlib 그림 이름 그대로
TOOL_ICONS = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9v11h14V9"/><path d="M10 20v-6h4v6"/>',
    "back": '<path d="M19 12H5"/><path d="M11 6l-6 6 6 6"/>',
    "forward": '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
    "move": '<path d="M12 3v18M3 12h18"/><path d="M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/>',
    "zoom_to_rect": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5M11 8v6M8 11h6"/>',
    "subplots": '<path d="M4 6h10M4 12h4M12 12h8M4 18h12"/>'
                '<circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "qt4_editor_options": '<path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="M13 7l4 4"/>',
    "filesave": '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M5 20h14"/>',
}


def tool_icon(name: str) -> QIcon:
    """회색 선 아이콘, 눌린 상태(이동·확대 켜짐)는 파랑."""
    icon = QIcon()
    for color, state in ((GREY_700, QIcon.State.Off), (BLUE, QIcon.State.On)):
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" '
               f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
               f'{TOOL_ICONS[name]}</svg>')
        pm = QPixmap()
        pm.loadFromData(svg.encode(), "SVG")
        icon.addPixmap(pm, QIcon.Mode.Normal, state)
    return icon


class ToolBar(NavigationToolbar2QT):
    """matplotlib 도구 막대에 테마 아이콘을 씌운 것."""

    def _icon(self, name):
        stem = name.rsplit(".", 1)[0]
        return tool_icon(stem) if stem in TOOL_ICONS else super()._icon(name)


def card(w: QWidget, margins: int = 16) -> QWidget:
    """흰 카드로 만든다(스타일시트 #card). 안쪽 여백도 맞춤."""
    w.setObjectName("card")
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    if w.layout() is not None:
        w.layout().setContentsMargins(margins, margins, margins, margins)
    return w


def primary(b):
    """핵심 동작 버튼(파란 면)."""
    b.setProperty("primary", True)
    return b


def section(text: str):
    from PySide6.QtWidgets import QLabel

    lab = QLabel(text)
    lab.setObjectName("section")
    return lab


def hint(text: str):
    from PySide6.QtWidgets import QLabel

    lab = QLabel(text)
    lab.setObjectName("hint")
    lab.setWordWrap(True)
    return lab


def roomy(root: QWidget) -> None:
    """폼 줄 간격을 넉넉히(토스처럼 여백으로 구분), 조작 칸 스크롤은 세로만. 이미 만든 화면 전체에 한 번."""
    from PySide6.QtWidgets import QComboBox, QScrollArea

    for cb in root.findChildren(QComboBox):  # 긴 항목(모델 식 등) 때문에 칸이 창보다 넓어지지 않게
        cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        cb.setMinimumContentsLength(6)
    for sc in root.findChildren(QScrollArea):
        if sc.widget() is not None and sc.widget().findChildren(QFormLayout):
            sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    for f in root.findChildren(QFormLayout):
        f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)  # 좁으면 이름을 칸 위로(가로 넘침 대신)
        f.setVerticalSpacing(10)
        f.setHorizontalSpacing(14)
        f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
