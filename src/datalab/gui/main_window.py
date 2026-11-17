"""메인 창: 시료 목록 | 그래프 | 옵션·결과."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QImage, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressDialog, QPushButton,
                               QScrollArea, QSplitter, QTableWidget, QTabWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from datalab import __author__, __version__
from datalab import db, updater
from datalab.analysis import vsm as vsm_an
from datalab.analysis import xrd as xrd_an
from datalab.io import load_any
from datalab.gui.update_worker import UpdateCheckWorker, UpdateDownloadWorker
from datalab.plot import figures

APP_TITLE = "DataLab"
OPEN_FILTER = "데이터 (*.csv *.txt *.dat *.xy *.xrdml *.rasx);;모든 파일 (*)"
TEMPLATE_DIR = Path.home() / "Documents" / "DataLab_Data" / "templates"  # CLAUDE.md: 사용자 데이터는 문서\DataLab_Data
SAVE_FILTER ="PNG 600 dpi (*.png);;SVG 벡터 (*.svg);;PDF 벡터 (*.pdf);;TIFF 600 dpi (*.tif)"
BATCH_EXT = {"PNG 600 dpi": ".png", "SVG 벡터": ".svg", "PDF 벡터": ".pdf", "TIFF 600 dpi": ".tif"}


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.5g}"
    return str(v)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} v{__version__} — 개발자 {__author__}")
        self.resize(1400, 820)
        self.setAcceptDrops(True)
        self.items: list[dict] = []  # {kind, name, data, xrd_result}
        self.fig = None

        # 왼쪽: 종류 + 시료 목록(체크한 것만 겹쳐 그림)
        self.mode = QComboBox()
        self.mode.addItems(["VSM", "XRD"])
        self.mode.currentTextChanged.connect(self._reset_axes)  # VSM·XRD 축 범위가 전혀 달라 종류를 바꾸면 비운다
        self.mode.currentTextChanged.connect(self._fill_list)
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.setToolTip("체크한 시료만 그림. 두 번 누르면 그래프 표시 이름을 바꿉니다.")
        self.list.itemChanged.connect(self._item_changed)
        self.list.itemSelectionChanged.connect(self._load_line)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.addWidget(self.mode)
        lv.addWidget(self.list)

        # 가운데: 그래프(프리셋 크기 그대로 — 화면과 저장이 같다)
        self.plot_box = QWidget()
        self.plot_layout = QVBoxLayout(self.plot_box)
        self.plot_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.plot_box)

        # 오른쪽: 옵션·결과
        self.style = QComboBox()
        self.style.addItems(list(figures.STYLES))
        self.font = QComboBox()
        self.font.addItems(figures.FONTS)
        self.bw = QCheckBox("흑백 출판(검정 + 선 모양으로 구분)")
        self.bw.setToolTip("선 색을 모두 검정으로, 시료마다 실선·파선·점선·일점쇄선. 직접 고른 색은 그대로 둡니다.")
        self.layout_box = QComboBox()
        self.layout_box.addItems(list(figures.LAYOUTS))
        self.layout_box.setToolTip("패널이 여럿이면 체크한 시료를 차례대로 나눠 그림. 그래프 편집 탭에서 시료별 패널을 정할 수 있습니다.")
        self.inset = QCheckBox("원점 확대 인셋")
        self.inset.setChecked(True)
        self.inset_w = self._spin(0, 1e6, 0, "자동", 1)
        self.h_unit = QComboBox()
        self.h_unit.addItems(["Oe", "kA/m"])
        self.offset = self._spin(-1e4, 1e4, 0, "", 0.01)
        self.bg = QCheckBox("고자장 배경 기울기 빼기")
        self.bg.setToolTip("홀더·반자성·상자성 배경(직선 χH)을 빼고 Ms·Hc를 다시 계산합니다. 기울기는 결과 표에 나옵니다.")
        self.bg_frac = self._spin(10, 99, 70, "", 5)
        self.bg_frac.setSuffix(" %")
        self.bg_frac.setToolTip("|H|가 H 최대의 이 비율 이상인 점으로 기울기를 맞춤")
        self.vsm_y = QComboBox()
        self.vsm_y.addItems(["M", "dM/dH"])
        self.vsm_y.setToolTip("dM/dH: 스위칭 자장 분포(SFD). 인셋은 그리지 않습니다.")
        self.smooth = self._spin(0, 101, 0, "없음", 2)
        self.smooth.setDecimals(0)
        self.smooth.setSuffix(" 점")
        self.smooth.setToolTip("dM/dH 평활화: M을 이 점 수로 이동평균한 뒤 미분(잡음이 많아 뾰족할 때). 결과 표 값은 바뀌지 않음")
        self.wf = self._spin(0, 5, 0, "", 0.1)
        self.norm = QCheckBox("최댓값 1로 정규화")
        self.norm.setChecked(True)
        for w in (self.style, self.font, self.h_unit, self.layout_box, self.vsm_y):
            w.currentTextChanged.connect(lambda _: self.redraw())
        for w in (self.inset, self.norm, self.bw, self.bg):
            w.toggled.connect(lambda _: self.redraw())
        for w in (self.inset_w, self.offset, self.wf, self.bg_frac, self.smooth):
            w.valueChanged.connect(lambda _: self.redraw())
        form = QFormLayout()
        form.addRow("스타일", self.style)
        form.addRow("글꼴", self.font)
        form.addRow(self.bw)
        form.addRow("배치", self.layout_box)
        form.addRow(QLabel("<b>VSM</b>"))
        form.addRow(self.inset)
        form.addRow("인셋 H 반폭", self.inset_w)
        form.addRow("H 표시 단위", self.h_unit)
        form.addRow("자장 오프셋 보정(Oe)", self.offset)
        form.addRow(self._row(self.bg, QLabel("맞춤 |H| ≥"), self.bg_frac))
        form.addRow("세로축", self._row(self.vsm_y, QLabel("평활화"), self.smooth))
        form.addRow(QLabel("<b>XRD</b>"))
        form.addRow(self.norm)
        form.addRow("세로 띄우기(waterfall)", self.wf)
        edit = QFormLayout()
        self._edit_panel(edit)
        self.table = QTableWidget()
        copy = QPushButton("결과 표 복사(Excel 붙여넣기)")
        copy.clicked.connect(self.copy_table)
        right = QWidget()
        rv = QVBoxLayout(right)
        tabs = QTabWidget()
        for lay, title in ((form, "옵션"), (edit, "그래프 편집")):
            page = QWidget()
            page.setLayout(lay)
            tabs.addTab(page, title)
        rv.addWidget(tabs)
        rv.addWidget(self.table, 1)
        rv.addWidget(copy)

        split = QSplitter()
        for w, s in ((left, 220), (scroll, 800), (right, 380)):
            split.addWidget(w)
        split.setSizes([220, 800, 380])
        self.setCentralWidget(split)
        self.status = QLabel()
        self.statusBar().addWidget(self.status, 1)
        self._menus()
        self.redraw()
        self._update_check = self._update_dl = None
        if updater.install_dir():  # exe로 실행할 때만 시작 시 조용히 확인(개발·테스트에서는 네트워크 안 씀)
            QTimer.singleShot(2000, lambda: self.check_updates(silent=True))

    def _edit_panel(self, form: QFormLayout):
        """그래프 편집(Origin Format › Axes·Plot). 빈 칸·0은 자동."""
        form.addRow(QLabel("빈 칸·0 = 자동"))
        self.ax_w = {}
        for a in "xy":
            w = {"min": QLineEdit(), "max": QLineEdit(), "step": self._spin(0, 1e9, 0, "자동", 1),
                 "log": QCheckBox("로그"), "title": QLineEdit()}
            w["min"].setPlaceholderText("최소")
            w["max"].setPlaceholderText("최대")
            w["title"].setPlaceholderText("기본 (수식: $M_s$, $\\mu_0H$)")
            w["title"].setToolTip("$...$ 안은 수식(위첨자 ^, 아래첨자 _, \\mu 등). 수식과 한글을 함께 쓰면 그 제목은 맑은 고딕으로 나옵니다.")
            for k in ("min", "max", "title"):
                w[k].editingFinished.connect(self.redraw)
            w["step"].valueChanged.connect(lambda _: self.redraw())
            w["log"].toggled.connect(lambda _: self.redraw())
            form.addRow(f"{a.upper()} 범위", self._row(w["min"], QLabel("~"), w["max"]))
            form.addRow(f"{a.upper()} 눈금 간격", self._row(w["step"], w["log"]))
            form.addRow(f"{a.upper()} 축 제목", w["title"])
            self.ax_w[a] = w
        self.y2title = QLineEdit()
        self.y2title.setPlaceholderText("기본(왼쪽과 같음)")
        self.y2title.editingFinished.connect(self.redraw)
        form.addRow("오른쪽 Y 축 제목", self.y2title)
        self.legend = QComboBox()
        self.legend.addItems(list(figures.LEGEND_LOC))
        self.legend.currentTextChanged.connect(lambda _: self.redraw())
        form.addRow("범례", self.legend)
        # 선택 시료 선 모양 — 시료 dict의 "style"에 저장
        self.color_btn = QPushButton("색")
        self.color_btn.clicked.connect(self._pick_color)
        self.lw = self._spin(0, 10, 0, "기본", 0.25)
        self.marker = QComboBox()
        self.marker.addItems(list(figures.MARKERS))
        self.lw.valueChanged.connect(lambda v: self._set_line(lw=v))
        self.marker.currentTextChanged.connect(lambda t: self._set_line(marker=figures.MARKERS[t]))
        reset = QPushButton("기본")
        reset.clicked.connect(lambda: self._set_line(color=None, lw=0, marker="", reload=True))
        form.addRow("선택 시료 선", self._row(self.color_btn, self.lw, self.marker, reset))
        self.panel = QComboBox()
        self.panel.addItems(["패널 자동", "패널 1", "패널 2", "패널 3", "패널 4"])
        self.panel.currentIndexChanged.connect(lambda i: self._set_line(panel=i))
        self.right = QCheckBox("오른쪽 Y축")
        self.right.setToolTip("Double-Y: 눈금이 다른 시료를 같은 패널 오른쪽 축에 그림")
        self.right.toggled.connect(lambda v: self._set_line(right=v))
        form.addRow("선택 시료 위치", self._row(self.panel, self.right))

    @staticmethod
    def _row(*widgets) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        for w in widgets:
            h.addWidget(w)
        return box

    def _axes_opts(self) -> dict:
        o = {"legend": self.legend.currentText(), "y2title": self.y2title.text()}
        for a, w in self.ax_w.items():
            for k in ("min", "max"):
                try:
                    o[a + k] = float(w[k].text())
                except ValueError:
                    o[a + k] = None
            o.update({a + "step": w["step"].value(), a + "log": w["log"].isChecked(), a + "title": w["title"].text()})
        return o

    # ------------------------------------------------------------ 그래프 템플릿(Origin Save Template·Copy Format)
    def template(self) -> dict:
        """지금 그래프 모양. 자장 오프셋은 측정 보정값이라 넣지 않는다. lines는 체크한 시료 순서대로."""
        o = self._axes_opts()
        return {"datalab_template": 1, "mode": self.mode.currentText(), "style": self.style.currentText(),
                "font": self.font.currentText(), "bw": self.bw.isChecked(), "layout": self.layout_box.currentText(), "inset": self.inset.isChecked(),
                "inset_w": self.inset_w.value(), "h_unit": self.h_unit.currentText(), "vsm_y": self.vsm_y.currentText(), "smooth": self.smooth.value(),
                "norm": self.norm.isChecked(), "wf": self.wf.value(),
                "legend": o["legend"], "y2title": o["y2title"],
                "axes": {a: {k: o[a + k] for k in ("min", "max", "step", "log", "title")} for a in "xy"},
                "lines": [dict(it.get("style", {})) for it in self.checked()]}

    def apply_template(self, t: dict):
        """template() 값을 화면에 넣고 한 번만 다시 그림. 모르는 값(다른 버전·손으로 고친 파일)은 건너뜀."""
        if not isinstance(t, dict) or t.get("datalab_template") != 1:
            raise ValueError("DataLab 그래프 템플릿 파일이 아닙니다.")
        self._hold = True
        try:
            if t.get("mode") in ("VSM", "XRD"):
                self.mode.setCurrentText(t["mode"])  # 축 값을 비우므로 먼저
            for box, key, opts in ((self.style, "style", figures.STYLES), (self.font, "font", figures.FONTS),
                                   (self.layout_box, "layout", figures.LAYOUTS),
                                   (self.h_unit, "h_unit", ("Oe", "kA/m")), (self.vsm_y, "vsm_y", ("M", "dM/dH")),
                                   (self.legend, "legend", figures.LEGEND_LOC)):
                if t.get(key) in opts:
                    box.setCurrentText(t[key])
            for chk, key in ((self.inset, "inset"), (self.norm, "norm"), (self.bw, "bw")):
                if key in t:
                    chk.setChecked(bool(t[key]))
            for spin, key in ((self.inset_w, "inset_w"), (self.wf, "wf"), (self.smooth, "smooth")):
                if isinstance(t.get(key), (int, float)):
                    spin.setValue(t[key])
            self.y2title.setText(str(t.get("y2title") or ""))
            for a, w in self.ax_w.items():
                v = (t.get("axes") or {}).get(a) or {}
                for k in ("min", "max"):
                    w[k].setText("" if v.get(k) is None else f"{float(v[k]):g}")
                w["step"].setValue(float(v.get("step") or 0))
                w["log"].setChecked(bool(v.get("log")))
                w["title"].setText(str(v.get("title") or ""))
            keys = ("color", "lw", "marker", "panel", "right")
            for it, st in zip(self.checked(), t.get("lines") or []):
                if isinstance(st, dict):
                    it["style"] = {k: st[k] for k in keys if k in st}
                    if it["style"].get("marker") not in figures.MARKERS.values():
                        it["style"].pop("marker", None)  # _load_line이 목록에 없는 기호면 멈춤
        finally:
            self._hold = False
        self._load_line()
        self.redraw()

    def save_template(self):
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "그래프 템플릿 저장", str(TEMPLATE_DIR / "그래프.json"),
                                              "그래프 템플릿 (*.json)")
        if path:
            Path(path).write_text(json.dumps(self.template(), ensure_ascii=False, indent=1), encoding="utf-8")
            self.status.setText(f"템플릿 저장: {path}")

    def load_template(self):
        path, _ = QFileDialog.getOpenFileName(self, "그래프 템플릿 불러오기", str(TEMPLATE_DIR), "그래프 템플릿 (*.json)")
        if not path:
            return
        try:
            self.apply_template(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, AttributeError) as e:
            self.redraw()  # 중간까지 들어간 값이라도 화면과 그래프를 맞춤
            QMessageBox.warning(self, "템플릿 불러오기 실패", f"{path}\n{e}")
            return
        self.status.setText(f"템플릿 적용: {Path(path).name}")

    def _reset_axes(self):
        for w in self.ax_w.values():
            for k in ("min", "max", "title"):
                w[k].clear()
            for k in ("step", "log"):
                w[k].blockSignals(True)
            w["step"].setValue(0)
            w["log"].setChecked(False)
            for k in ("step", "log"):
                w[k].blockSignals(False)
        self.y2title.clear()
        self.legend.blockSignals(True)
        self.legend.setCurrentText("자동")
        self.legend.blockSignals(False)

    def _selected_items(self) -> list[dict]:
        return [self.items[li.data(Qt.ItemDataRole.UserRole)] for li in self.list.selectedItems()]

    def _item_changed(self, li: QListWidgetItem):
        it = self.items[li.data(Qt.ItemDataRole.UserRole)]
        it["name"] = li.text().strip() or it["name"]
        self.redraw()

    def _load_line(self):
        sel = self._selected_items()
        st = sel[0].get("style", {}) if sel else {}
        widgets = (self.lw, self.marker, self.panel, self.right)
        for w in widgets:
            w.blockSignals(True)
        self.lw.setValue(st.get("lw") or 0)
        self.marker.setCurrentText(next(k for k, v in figures.MARKERS.items() if v == (st.get("marker") or "")))
        self.panel.setCurrentIndex(st.get("panel") or 0)
        self.right.setChecked(bool(st.get("right")))
        for w in widgets:
            w.blockSignals(False)
        self.color_btn.setStyleSheet(f"background:{st['color']}" if st.get("color") else "")

    def _pick_color(self):
        sel = self._selected_items()
        if not sel:
            self.status.setText("목록에서 시료를 먼저 고르세요.")
            return
        c = QColorDialog.getColor(QColor(sel[0].get("style", {}).get("color") or "#1f77b4"), self, "선 색")
        if c.isValid():
            self._set_line(color=c.name())

    def _set_line(self, reload: bool = False, **kw):
        sel = self._selected_items()
        if not sel:
            self.status.setText("목록에서 시료를 먼저 고르세요.")
            return
        for it in sel:
            it.setdefault("style", {}).update(kw)
        if reload or "color" in kw:
            self._load_line()
        self.redraw()

    def _spin(self, lo, hi, val, special, step) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(3)
        s.setSingleStep(step)
        s.setValue(val)
        if special:
            s.setSpecialValueText(special)
        return s

    def _menus(self):
        m = self.menuBar().addMenu("파일")
        for text, key, fn in (("열기...", QKeySequence.StandardKey.Open, self.open_dialog),
                              ("그림 저장(PNG·SVG·PDF)...", QKeySequence.StandardKey.Save, self.save_dialog),
                              ("일괄 내보내기(시료마다 한 장)...", "Ctrl+Shift+S", self.batch_dialog),
                              ("그림 클립보드 복사(PPT 붙여넣기)", "Ctrl+Shift+C", self.copy_figure),
                              ("그래프 템플릿 저장...", "Ctrl+Shift+T", self.save_template),
                              ("그래프 템플릿 불러오기...", "Ctrl+T", self.load_template),
                              ("체크한 시료 DB에 저장", "Ctrl+D", self.save_to_db),
                              ("DB 목록·태깅...", "Ctrl+L", self.db_dialog),
                              ("선택 시료 지우기", QKeySequence.StandardKey.Delete, self.remove_selected)):
            a = QAction(text, self)
            a.setShortcut(key)
            a.triggered.connect(fn)
            m.addAction(a)
            self.addAction(a)
        h = self.menuBar().addMenu("도움말")
        h.addAction("업데이트 확인...", lambda: self.check_updates(silent=False))
        h.addAction("정보", self.show_about)

    # ------------------------------------------------------------ 파일
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.open_paths([u.toLocalFile() for u in e.mimeData().urls()])

    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "파일 열기", "", OPEN_FILTER)
        self.open_paths(paths)

    def open_paths(self, paths: list[str], names: dict[str, str] | None = None):
        """names = {경로: 표시 이름} — DB에서 연 원본 사본(이름이 SHA256)에 시료 이름을 붙일 때."""
        files = []
        for p in map(Path, paths):
            files += sorted(f for f in p.iterdir() if f.is_file()) if p.is_dir() else [p]
        errors, kind = [], None
        for f in files:
            try:
                kind, data = load_any(f)
            except Exception as e:
                errors.append(str(e))
                continue
            item = {"kind": kind, "name": (names or {}).get(str(f)) or getattr(data, "sample_id", None)
                    or data.sample_name, "data": data}
            if kind == "XRD":
                self.status.setText(f"XRD 해석 중: {f.name}")
                QApplication.processEvents()
                # shortcut: 해석을 화면 스레드에서 돌림(파일당 1초 안팎), 수십 개씩 열면 작업 스레드로
                try:
                    item["xrd_result"] = xrd_an.analyze(data)
                except Exception as e:
                    errors.append(f"{f.name}: XRD 해석 실패 ({e})")
                    continue
            self.items.append(item)
        self.status.setText(f"{len(files) - len(errors)}개 열림" + (f", {len(errors)}개 실패" if errors else ""))
        if errors:
            QMessageBox.warning(self, "열지 못한 파일", "\n".join(errors[:20]))
        if kind and self.mode.currentText() != kind:
            self.mode.setCurrentText(kind)  # _fill_list 호출
        else:
            self._fill_list()

    def save_to_db(self) -> tuple[int, int]:
        """체크한 시료의 원본·해석 결과를 DB에 기록한다. VSM 결과는 보정(오프셋·배경) 전 원본 값. 돌려줌: (새로, 갱신)."""
        sel = self.checked()
        if not sel:
            self.status.setText("DB에 저장할 시료를 체크하세요")
            return 0, 0
        store = db.Store(getattr(self, "db_root", db.DATA_DIR))
        new = upd = 0
        try:
            for it in sel:
                d = it["data"]
                if it["kind"] == "VSM":
                    r = vsm_an.analyze_loop(d.h, d.m)
                    hu, mu = d.h_unit, d.m_unit
                    units = {"Hc": hu, "Hc_half": hu, "H_bias": hu, "Mr": mu, "Ms": mu, "SQ": "", "H_max": hu}
                    res = {k: (r[k], u) for k, u in units.items()}
                    args = (d.path, "VSM", it["name"], res, vsm_an.ANALYSIS_VERSION, None,
                            d.file_format, {**d.meta, "device": d.device})
                else:
                    import xrdcheck
                    res = {k: (v, "") for k, v in xrd_an.summary(it["xrd_result"]).items()}  # 단위는 열 이름 안에
                    md = d.measurement_date
                    args = (d.source_path, "XRD", it["name"], res, f"xrdcheck-{xrdcheck.__version__}",
                            md.isoformat() if md else None, None, None)
                _, is_new = store.add_measurement(*args)
                new += is_new
                upd += not is_new
            n_s, n_m = store.counts()
        except OSError as e:
            QMessageBox.warning(self, "DB 저장 실패", str(e))
            return new, upd
        finally:
            store.close()
        self.status.setText(f"DB 저장: 새로 {new}개, 결과 갱신 {upd}개 (전체 시료 {n_s}개·측정 {n_m}개)")
        return new, upd

    def db_dialog(self):
        from datalab.gui.db_dialog import DbDialog

        self._db_dlg = DbDialog(self, getattr(self, "db_root", db.DATA_DIR))
        self._db_dlg.show()

    def remove_selected(self):
        gone = {i.data(Qt.ItemDataRole.UserRole) for i in self.list.selectedItems()}
        self.items = [it for n, it in enumerate(self.items) if n not in gone]
        self._fill_list()

    def _fill_list(self):
        self.list.blockSignals(True)
        self.list.clear()
        for n, it in enumerate(self.items):
            if it["kind"] == self.mode.currentText():
                li = QListWidgetItem(it["name"])
                li.setFlags(li.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable)
                li.setCheckState(Qt.CheckState.Checked)
                li.setData(Qt.ItemDataRole.UserRole, n)  # dict는 Qt 변환으로 복사되므로 번호만
                li.setToolTip(str(it["data"].path if it["kind"] == "VSM" else it["data"].source_path))
                self.list.addItem(li)
        self.list.blockSignals(False)
        self.redraw()

    def checked(self) -> list[dict]:
        return [self.items[self.list.item(i).data(Qt.ItemDataRole.UserRole)] for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]

    # ------------------------------------------------------------ 그리기·결과
    def redraw(self):
        if getattr(self, "_hold", False):  # 템플릿 적용 중 — 값마다 다시 그리지 않음
            return
        sel = self.checked()
        self.fig, rows = self._figure(sel, self.layout_box.currentText())
        self._show_table(sel, rows)
        while self.plot_layout.count():
            w = self.plot_layout.takeAt(0).widget()
            w.hide()  # deleteLater는 다음 이벤트 때 지워져 그 사이 옛 그래프가 겹쳐 보임
            w.deleteLater()
        canvas = FigureCanvasQTAgg(self.fig)
        w, h = (self.fig.get_size_inches() * self.fig.dpi).astype(int)
        canvas.setFixedSize(int(w), int(h))
        self.plot_layout.addWidget(NavigationToolbar2QT(canvas, self.plot_box))
        self.plot_layout.addWidget(canvas)
        try:
            canvas.draw()
        except ValueError as e:  # 축 제목 $...$ 수식 오류 — 글자 그대로 보이게 바꿔 다시 그림
            for lab in (lb for a in self.fig.axes for lb in (a.xaxis.label, a.yaxis.label)):
                lab.set_text(lab.get_text().replace("$", r"\$"))
            canvas.draw()
            self.status.setText("축 제목 수식 오류: " + str(e).splitlines()[0])

    def _figure(self, sel: list[dict], layout: str):
        """지금 옵션·편집 값으로 새 Figure와 결과 표 행을 만든다(화면·일괄 내보내기 공용)."""
        figures.apply_style(self.style.currentText(), self.font.currentText(), self.bw.isChecked())
        fig = figures.new_figure(self.style.currentText())
        if self.mode.currentText() == "VSM":
            rows, panels = self._draw_vsm(fig, sel, layout)
        else:
            panels = figures.draw_xrd(fig, [(it["name"], it["data"].two_theta, it["data"].counts,
                                             it.get("style", {})) for it in sel],
                                      self.wf.value(), self.norm.isChecked(), layout)
            rows = [xrd_an.summary(it["xrd_result"]) for it in sel]
        o = self._axes_opts()
        for ax in panels:
            figures.apply_axes(ax, o)
        return fig, rows

    def _draw_vsm(self, fig, sel: list[dict], layout: str) -> tuple[list[dict], list]:
        off = self.offset.value()
        ka = self.h_unit.currentText() == "kA/m"
        k = vsm_an.OE_TO_A_PER_M / 1000 if ka else 1.0
        deriv = self.vsm_y.currentText() == "dM/dH"
        data, rows = [], []
        for it in sel:
            d = it["data"]
            scale = k if d.h_unit == "Oe" else 1.0
            hu, mu = ("kA/m" if ka and d.h_unit == "Oe" else d.h_unit), d.m_unit
            chi = vsm_an.high_field_slope(d.h - off, d.m, self.bg_frac.value() / 100) if self.bg.isChecked() else None
            m = d.m - (chi or 0) * (d.h - off)
            hp = (d.h - off) * scale
            data.append((it["name"], hp, vsm_an.dmdh(hp, m, int(self.smooth.value())) if deriv else m, it.get("style", {})))
            raw = vsm_an.analyze_loop(d.h, d.m)
            r = vsm_an.analyze_loop(d.h, d.m, off, chi or 0) if off or chi else raw
            hs = lambda v: v * scale if v is not None else None  # noqa: E731
            row = {"형식": d.file_format, f"Hc ({hu})": hs(r["Hc"]), f"Hc 반폭 ({hu})": hs(r["Hc_half"]),
                   f"H 치우침 ({hu})": hs(r["H_bias"]), f"Mr ({mu})": r["Mr"], f"Ms ({mu})": r["Ms"],
                   "Mr/Ms": r["SQ"], f"H 최대 ({hu})": hs(r["H_max"])}
            if off or chi:
                row[f"Hc 보정 전 ({hu})"] = hs(raw["Hc"])
            if self.bg.isChecked():
                row[f"배경 기울기 χ ({mu}/{hu})"] = chi / scale if chi is not None else "맞춤 점 부족"
                row[f"Ms 보정 전 ({mu})"] = raw["Ms"]
            row["장비 값 대조"] = ("; ".join(vsm_an.compare_device(raw, d.device)) or "일치") if d.device else "장비 값 없음"
            row["해석 버전"] = vsm_an.ANALYSIS_VERSION
            rows.append(row)
        u = sel[0]["data"] if sel else None
        h_label = "H (kA/m)" if ka and (u is None or u.h_unit == "Oe") else f"H ({u.h_unit if u else 'Oe'})"
        mu = u.m_unit if u else "emu/g"
        m_label = f"dM/dH ({mu}/{h_label[3:-1]})" if deriv else f"M ({mu})"
        panels = figures.draw_vsm(fig, data, h_label, m_label, self.inset.isChecked() and not deriv,
                                  self.inset_w.value() * (k if u and u.h_unit == "Oe" else 1) or None, layout)
        return rows, panels

    def _show_table(self, sel: list[dict], rows: list[dict]):
        keys = list(dict.fromkeys(k for r in rows for k in r))
        self.table.clear()
        self.table.setRowCount(len(keys))
        self.table.setColumnCount(len(sel))
        self.table.setVerticalHeaderLabels(keys)
        self.table.setHorizontalHeaderLabels([it["name"] for it in sel])
        for c, r in enumerate(rows):
            for i, k in enumerate(keys):
                self.table.setItem(i, c, QTableWidgetItem(_fmt(r.get(k))))
        self.table.resizeColumnsToContents()

    # ------------------------------------------------------------ 내보내기
    def save_dialog(self):
        sel = self.checked()
        default = sel[0]["name"] if sel else "graph"
        path, _ = QFileDialog.getSaveFileName(self, "그림 저장", default + ".png", SAVE_FILTER)
        if path:
            figures.save(self.fig, path)
            self.status.setText(f"저장: {path}")

    def batch_export(self, folder: str | Path, ext: str) -> list[Path]:
        """체크한 시료마다 한 장씩 같은 스타일로 저장(Origin Batch Plotting). 한 장에 시료 하나라 배치·오른쪽 Y축은 뺀다."""
        paths = []
        for it, path in zip(self.checked(), self._batch_paths(folder, ext)):
            one = {**it, "style": {k: v for k, v in it.get("style", {}).items() if k not in ("panel", "right")}}
            fig, _ = self._figure([one], "한 그래프")
            paths.append(figures.save(fig, path))
        return paths

    def _batch_paths(self, folder: str | Path, ext: str) -> list[Path]:
        """시료 이름 → 파일 경로. Windows에 못 쓰는 글자는 _, 같은 이름은 _2·_3을 붙여 서로 덮어쓰지 않게."""
        out, used = [], set()
        for it in self.checked():
            stem = re.sub(r'[\\/:*?"<>|]', "_", it["name"]).strip(" .") or "graph"
            name, n = stem, 1
            while name.lower() in used:
                n += 1
                name = f"{stem}_{n}"
            used.add(name.lower())
            out.append(Path(folder) / (name + ext))
        return out

    def batch_dialog(self):
        if not self.checked():
            self.status.setText("체크한 시료가 없습니다.")
            return
        ext, ok = QInputDialog.getItem(self, "일괄 내보내기", "형식 (체크한 시료마다 한 장, 파일 이름 = 시료 이름)",
                                       list(BATCH_EXT), 0, False)
        if not ok:
            return
        folder = QFileDialog.getExistingDirectory(self, "저장할 폴더")
        if not folder:
            return
        ext = BATCH_EXT[ext]
        exist = [p.name for p in self._batch_paths(folder, ext) if p.exists()]
        if exist and QMessageBox.question(self, "덮어쓰기", f"같은 이름 파일이 {len(exist)}개 있습니다. 덮어쓸까요?\n"
                                          + "\n".join(exist[:10])) != QMessageBox.StandardButton.Yes:
            return
        try:
            paths = self.batch_export(folder, ext)
        except OSError as e:
            QMessageBox.warning(self, "일괄 내보내기 실패", str(e))
        else:
            self.status.setText(f"{len(paths)}장 저장: {folder}")
        finally:
            self.redraw()  # 화면 그래프의 전역 스타일 상태를 되돌림

    def copy_figure(self):
        QApplication.clipboard().setImage(QImage.fromData(figures.png_bytes(self.fig)))
        self.status.setText("그림을 클립보드에 복사했습니다(300 dpi).")

    def copy_table(self):
        t = self.table
        heads = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
        lines = ["\t" + "\t".join(heads)]
        for r in range(t.rowCount()):
            cells = [(t.item(r, c).text() if t.item(r, c) else "") for c in range(t.columnCount())]
            lines.append(t.verticalHeaderItem(r).text() + "\t" + "\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))
        self.status.setText("결과 표를 복사했습니다.")

    # ------------------------------------------------------------ 정보·자동 업데이트(xrdcheck GUI와 같은 흐름)
    def show_about(self):
        cfg = updater.load_config(updater.config_dir())
        QMessageBox.about(self, "정보", f"<b>{APP_TITLE}</b> v{__version__}<br>개발자: {__author__}<br><br>"
                          "VSM·XRD 해석과 논문·PPT용 그래프, 측정 이력 DB"
                          f"<br><br>업데이트 출처: {updater.source_label(cfg)}")

    def check_updates(self, silent: bool = False):
        """silent: 시작할 때 자동 확인 — 실패하거나 최신이면 아무것도 띄우지 않는다."""
        if self._update_check is not None and self._update_check.isRunning():
            return
        w = UpdateCheckWorker(updater.load_config(updater.config_dir()), self)
        w.found.connect(lambda rel: self._on_update_found(rel, silent))
        w.failed.connect(lambda msg: silent or QMessageBox.warning(self, "업데이트", msg))
        self._update_check = w
        if not silent:
            self.status.setText("업데이트 확인 중...")
        w.start()

    def _on_update_found(self, rel, silent: bool):
        if rel is None:
            if not silent:
                self.status.setText(f"최신 버전입니다(v{__version__}).")
                QMessageBox.information(self, "업데이트", f"지금 쓰는 v{__version__}이 최신 버전입니다.")
            return
        self.status.setText(f"새 버전 v{rel.version}이 있습니다 — 도움말 > 업데이트 확인")
        box = QMessageBox(self)
        box.setWindowTitle("업데이트")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(f"새 버전 <b>v{rel.version}</b>이 있습니다(지금 v{__version__}).<br>지금 업데이트할까요?")
        box.setInformativeText("업데이트하면 프로그램을 닫고 새 버전으로 바꾼 뒤 다시 엽니다. DB·설정은 그대로입니다.")
        if rel.notes:
            box.setDetailedText(rel.notes)
        now = box.addButton("지금 업데이트", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("나중에", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is now:
            self.start_update(rel)

    def start_update(self, rel):
        ok, why = updater.can_self_update()
        if not ok:
            if QMessageBox.question(self, "업데이트", why + "\n\n릴리스 위치를 열까요?") == QMessageBox.StandardButton.Yes \
                    and rel.page_url:
                url = rel.page_url
                QDesktopServices.openUrl(QUrl(url) if url.startswith("http") else QUrl.fromLocalFile(url))
            return
        dlg = QProgressDialog(f"v{rel.version} 내려받는 중...", "취소", 0, 0, self)
        dlg.setWindowTitle("업데이트")
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        w = UpdateDownloadWorker(rel, self)
        self._update_dl = w
        cancelled = []

        def on_progress(done_kb: int, total_kb: int):
            if total_kb and not cancelled:
                dlg.setMaximum(total_kb)
                dlg.setValue(min(done_kb, total_kb))
                dlg.setLabelText(f"v{rel.version} 내려받는 중... {done_kb / 1024:.0f} / {total_kb / 1024:.0f} MB")

        def on_ready(app_dir: str):
            dlg.close()
            if cancelled:
                return
            QMessageBox.information(self, "업데이트",
                                    f"v{rel.version}을 설치합니다. 프로그램이 잠시 닫혔다가 새 버전으로 다시 열립니다.")
            updater.launch_apply(Path(app_dir), updater.install_dir())
            self.close()
            QApplication.quit()

        def on_failed(msg: str):
            dlg.close()
            if not cancelled:
                QMessageBox.warning(self, "업데이트", msg)

        w.progress.connect(on_progress)
        w.ready.connect(on_ready)
        w.failed.connect(on_failed)
        dlg.canceled.connect(lambda: cancelled.append(True))
        w.start()
