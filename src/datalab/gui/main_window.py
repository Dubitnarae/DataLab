"""메인 창: 시료 목록 | 그래프 | 옵션·결과."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QImage, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from datalab import __author__, __version__
from datalab.analysis import vsm as vsm_an
from datalab.analysis import xrd as xrd_an
from datalab.io import load_any
from datalab.plot import figures

APP_TITLE = "DataLab"
OPEN_FILTER = "데이터 (*.csv *.txt *.dat *.xy *.xrdml *.rasx);;모든 파일 (*)"
SAVE_FILTER = "PNG 600 dpi (*.png);;SVG 벡터 (*.svg);;PDF 벡터 (*.pdf);;TIFF 600 dpi (*.tif)"


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
        self.mode.currentTextChanged.connect(self._fill_list)
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.itemChanged.connect(lambda _: self.redraw())
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
        self.inset = QCheckBox("원점 확대 인셋")
        self.inset.setChecked(True)
        self.inset_w = self._spin(0, 1e6, 0, "자동", 1)
        self.h_unit = QComboBox()
        self.h_unit.addItems(["Oe", "kA/m"])
        self.offset = self._spin(-1e4, 1e4, 0, "", 0.01)
        self.wf = self._spin(0, 5, 0, "", 0.1)
        self.norm = QCheckBox("최댓값 1로 정규화")
        self.norm.setChecked(True)
        for w in (self.style, self.h_unit):
            w.currentTextChanged.connect(lambda _: self.redraw())
        for w in (self.inset, self.norm):
            w.toggled.connect(lambda _: self.redraw())
        for w in (self.inset_w, self.offset, self.wf):
            w.valueChanged.connect(lambda _: self.redraw())
        form = QFormLayout()
        form.addRow("스타일", self.style)
        form.addRow(QLabel("<b>VSM</b>"))
        form.addRow(self.inset)
        form.addRow("인셋 H 반폭", self.inset_w)
        form.addRow("H 표시 단위", self.h_unit)
        form.addRow("자장 오프셋 보정(Oe)", self.offset)
        form.addRow(QLabel("<b>XRD</b>"))
        form.addRow(self.norm)
        form.addRow("세로 띄우기(waterfall)", self.wf)
        self.table = QTableWidget()
        copy = QPushButton("결과 표 복사(Excel 붙여넣기)")
        copy.clicked.connect(self.copy_table)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.addLayout(form)
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
                              ("그림 클립보드 복사(PPT 붙여넣기)", "Ctrl+Shift+C", self.copy_figure),
                              ("선택 시료 지우기", QKeySequence.StandardKey.Delete, self.remove_selected)):
            a = QAction(text, self)
            a.setShortcut(key)
            a.triggered.connect(fn)
            m.addAction(a)
            self.addAction(a)

    # ------------------------------------------------------------ 파일
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.open_paths([u.toLocalFile() for u in e.mimeData().urls()])

    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "파일 열기", "", OPEN_FILTER)
        self.open_paths(paths)

    def open_paths(self, paths: list[str]):
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
            item = {"kind": kind, "name": getattr(data, "sample_id", None) or data.sample_name, "data": data}
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
                li.setFlags(li.flags() | Qt.ItemFlag.ItemIsUserCheckable)
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
        figures.apply_style(self.style.currentText())
        self.fig = figures.new_figure(self.style.currentText())
        sel = self.checked()
        if self.mode.currentText() == "VSM":
            rows = self._draw_vsm(sel)
        else:
            figures.draw_xrd(self.fig, [(it["name"], it["data"].two_theta, it["data"].counts) for it in sel],
                             self.wf.value(), self.norm.isChecked())
            rows = [xrd_an.summary(it["xrd_result"]) for it in sel]
        self._show_table(sel, rows)
        while self.plot_layout.count():
            w = self.plot_layout.takeAt(0).widget()
            w.deleteLater()
        canvas = FigureCanvasQTAgg(self.fig)
        w, h = (self.fig.get_size_inches() * self.fig.dpi).astype(int)
        canvas.setFixedSize(int(w), int(h))
        self.plot_layout.addWidget(NavigationToolbar2QT(canvas, self.plot_box))
        self.plot_layout.addWidget(canvas)
        canvas.draw()

    def _draw_vsm(self, sel: list[dict]) -> list[dict]:
        off = self.offset.value()
        ka = self.h_unit.currentText() == "kA/m"
        k = vsm_an.OE_TO_A_PER_M / 1000 if ka else 1.0
        data, rows = [], []
        for it in sel:
            d = it["data"]
            scale = k if d.h_unit == "Oe" else 1.0
            data.append((it["name"], (d.h - off) * scale, d.m))
            raw = vsm_an.analyze_loop(d.h, d.m)
            r = vsm_an.analyze_loop(d.h, d.m, off) if off else raw
            hu, mu = ("kA/m" if ka and d.h_unit == "Oe" else d.h_unit), d.m_unit
            hs = lambda v: v * scale if v is not None else None  # noqa: E731
            row = {"형식": d.file_format, f"Hc ({hu})": hs(r["Hc"]), f"Hc 반폭 ({hu})": hs(r["Hc_half"]),
                   f"H 치우침 ({hu})": hs(r["H_bias"]), f"Mr ({mu})": r["Mr"], f"Ms ({mu})": r["Ms"],
                   "Mr/Ms": r["SQ"], f"H 최대 ({hu})": hs(r["H_max"])}
            if off:
                row[f"Hc 보정 전 ({hu})"] = hs(raw["Hc"])
            row["장비 값 대조"] = ("; ".join(vsm_an.compare_device(raw, d.device)) or "일치") if d.device else "장비 값 없음"
            row["해석 버전"] = vsm_an.ANALYSIS_VERSION
            rows.append(row)
        u = sel[0]["data"] if sel else None
        h_label = "H (kA/m)" if ka and (u is None or u.h_unit == "Oe") else f"H ({u.h_unit if u else 'Oe'})"
        figures.draw_vsm(self.fig, data, h_label, f"M ({u.m_unit if u else 'emu/g'})", self.inset.isChecked(),
                         self.inset_w.value() * (k if u and u.h_unit == "Oe" else 1) or None)
        return rows

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
