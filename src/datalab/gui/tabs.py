"""메인 창 맨 위 탭(LCR Logger 와 같은 구성): 데이터 처리 · 피크 피팅 · 자기 포화 피팅 · 워크시트.

Origin 메뉴 대응(조사: 레퍼런스 프로그램 Origin8 X-Functions 옵션 목록, docs/ORIGIN_BENCHMARK.md):
- 데이터 처리: Set Display Range·Mark Data Range, Remove Bad Data Points(Mask), subtract_ref, smooth, integ1, interp1
- 피크 피팅: fitpeaks·nlfit(Gauss·Lorentz·Voigt·Pearson7)
- 자기 포화 피팅: FitFunc LANGEVIN + 포화 접근 법칙
- 워크시트: 표 보기·복사·CSV, Set Column Values(식으로 새 열 → 새 시료)
계산은 analysis/process.py·fit.py, 이 파일은 화면만.
"""

from __future__ import annotations

import csv
import dataclasses

import matplotlib
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
                               QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from PySide6.QtCore import Qt

from datalab.analysis import fit as fit_an
from datalab.analysis import process as proc_an
from datalab.analysis import xrd as xrd_an
from datalab.gui import theme

# 탭 그림은 그래프 탭 스타일(전역 rcParams, 논문·PPT용)과 상관없이 화면 테마 색
_RC = theme.PLOT_RC


def _num(edit: QLineEdit):
    try:
        return float(edit.text())
    except ValueError:
        return None


def _row(*widgets) -> QWidget:
    box = QWidget()
    h = QHBoxLayout(box)
    h.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        h.addWidget(w)
    return box


_wrap = theme.hint  # 회색 설명 글(줄바꿈)


def _fill_table(t: QTableWidget, headers: list[str], rows: list[list]):
    t.clear()
    t.setColumnCount(len(headers))
    t.setRowCount(len(rows))
    t.setHorizontalHeaderLabels(headers)
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            t.setItem(r, c, QTableWidgetItem("" if v is None else f"{v:.6g}" if isinstance(v, float) else str(v)))
    t.resizeColumnsToContents()


def _copy_table(t: QTableWidget) -> str:
    heads = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
    lines = ["\t".join(heads)]
    for r in range(t.rowCount()):
        lines.append("\t".join(t.item(r, c).text() if t.item(r, c) else "" for c in range(t.columnCount())))
    text = "\n".join(lines)
    QApplication.clipboard().setText(text)
    return text


class _Tab(QWidget):
    """대상 시료 고르기 + 그림 하나 + 결과 표. kinds: 고를 수 있는 시료 종류."""
    kinds = ("VSM", "XRD")

    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self._list: list[dict] = []
        self.target = QComboBox()
        self.target.currentIndexChanged.connect(lambda _: self._target_changed())
        self.fig = Figure(figsize=(6, 4.5), layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.table = QTableWidget()
        self.table.verticalHeader().setVisible(False)  # 줄 번호 대신 깔끔하게(첫 열이 이름)

    def _layout(self, controls: QWidget, table_title: str = "결과"):
        """왼쪽 조작 칸(스크롤) | 오른쪽 그림 카드 위·표 카드 아래. 조작 칸에 묶음 상자(카드)가 없으면 통째로 카드."""
        if not controls.findChildren(QGroupBox):
            theme.card(controls)
        else:
            controls.layout().setContentsMargins(0, 0, 4, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls)
        right = QSplitter(Qt.Orientation.Vertical)
        right.setHandleWidth(12)
        top = QWidget()
        tv = QVBoxLayout(top)
        tv.addWidget(NavigationToolbar2QT(self.canvas, top))
        tv.addWidget(self.canvas, 1)
        theme.card(top, 12)
        bottom = QWidget()
        bv = QVBoxLayout(bottom)
        bv.setSpacing(10)
        copy = QPushButton(f"{table_title} 표 복사(Excel 붙여넣기)")
        copy.clicked.connect(lambda: (_copy_table(self.table), self.mw.status.setText("표를 복사했습니다.")))
        bv.addWidget(theme.section(table_title))
        bv.addWidget(self.table, 1)
        bv.addWidget(copy)
        theme.card(bottom)
        right.addWidget(top)
        right.addWidget(bottom)
        right.setSizes([520, 260])
        split = QSplitter()
        split.setHandleWidth(12)
        split.addWidget(scroll)
        split.addWidget(right)
        split.setSizes([380, 900])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.addWidget(split)
        theme.roomy(self)

    def item(self) -> dict | None:
        i = self.target.currentIndex()
        return self._list[i] if 0 <= i < len(self._list) else None

    def refresh(self):
        """탭을 열 때·시료가 바뀔 때 대상 목록을 다시 채움(고르던 시료 유지)."""
        cur = self.item()
        self._list = [it for it in self.mw.items if it["kind"] in self.kinds]
        self.target.blockSignals(True)
        self.target.clear()
        self.target.addItems([f"{it['name']} ({it['kind']})" for it in self._list])
        self.target.setCurrentIndex(next((i for i, it in enumerate(self._list) if it is cur), 0) if self._list else -1)
        self.target.blockSignals(False)
        self._target_changed()

    def _target_changed(self):
        pass

    def _draw(self, fn):
        """fn(fig) 로 그리고 화면에 반영(탭 전용 글꼴·크기)."""
        with matplotlib.rc_context(_RC):
            self.fig.clear()
            fn(self.fig)
            self.canvas.draw()

    def _labels(self, it):
        return ("H (" + it["data"].h_unit + ")", "M (" + it["data"].m_unit + ")") if it["kind"] == "VSM" \
            else ("2θ (°)", "Intensity (counts)")


class ProcessTab(_Tab):
    """해석 구간·튀는 점 빼기·기준 곡선 빼기·평활화(그래프·해석에 반영) + 적분·보간(계산만)."""

    def __init__(self, mw):
        super().__init__(mw)
        self._drop: set[int] = set()
        self._cands: list[int] = []
        c = QWidget()
        v = QVBoxLayout(c)
        v.setSpacing(12)
        tc = QWidget()
        f = QFormLayout(tc)
        f.addRow("대상 시료", self.target)
        v.addWidget(theme.card(tc, 14))

        g = QGroupBox("해석 구간 (Origin Set Display Range)")
        gf = QFormLayout(g)
        self.xmin, self.xmax = QLineEdit(), QLineEdit()
        self.xmin.setPlaceholderText("처음부터")
        self.xmax.setPlaceholderText("끝까지")
        gf.addRow("X", _row(self.xmin, QLabel("~"), self.xmax))
        v.addWidget(g)

        g = QGroupBox("튀는 점 빼기 (Remove Bad Data Points — 원본은 그대로)")
        gv = QVBoxLayout(g)
        self.z = QSpinBox()
        self.z.setRange(3, 50)
        self.z.setValue(6)
        self.z.setToolTip("주변 중앙값에서 잡음(MAD)의 몇 배 넘게 벗어나면 후보")
        self.win = QSpinBox()
        self.win.setRange(3, 51)
        self.win.setSingleStep(2)
        self.win.setValue(7)
        find = QPushButton("후보 찾기")
        find.clicked.connect(self.find_spikes)
        gv.addWidget(_row(QLabel("기준 ×"), self.z, QLabel("창"), self.win, find))
        self.cand = QListWidget()
        self.cand.setMaximumHeight(110)
        gv.addWidget(self.cand)
        drop_c = QPushButton("체크한 후보 빼기")
        drop_c.clicked.connect(self.drop_checked)
        self.rlo, self.rhi = QLineEdit(), QLineEdit()
        self.rlo.setPlaceholderText("X부터")
        self.rhi.setPlaceholderText("X까지")
        drop_r = QPushButton("X 범위 점 빼기")
        drop_r.clicked.connect(self.drop_range)
        gv.addWidget(drop_c)
        gv.addWidget(_row(self.rlo, self.rhi, drop_r))
        undo = QPushButton("뺀 점 모두 되돌리기")
        undo.clicked.connect(self.undrop)
        self.drop_label = QLabel()
        gv.addWidget(_row(self.drop_label, undo))
        v.addWidget(g)

        g = QGroupBox("기준 곡선 빼기 (subtract_ref — 빈 홀더·기판 측정)")
        gf = QFormLayout(g)
        self.ref = QComboBox()
        self.common = QCheckBox("공통 구간만 빼기(기준 범위 밖 점은 버림)")
        gf.addRow("기준 시료", self.ref)
        gf.addRow(self.common)
        v.addWidget(g)

        g = QGroupBox("평활화 (smooth)")
        gf = QFormLayout(g)
        self.sm = QComboBox()
        self.sm.addItems(["없음", "이동평균", "Savitzky-Golay"])
        self.sm_n = QSpinBox()
        self.sm_n.setRange(3, 201)
        self.sm_n.setSingleStep(2)
        self.sm_n.setValue(5)
        self.sm_o = QSpinBox()
        self.sm_o.setRange(1, 5)
        self.sm_o.setValue(2)
        gf.addRow("방법", self.sm)
        gf.addRow("창(점)", _row(self.sm_n, QLabel("다항 차수(S-G)"), self.sm_o))
        v.addWidget(g)

        apply_b = QPushButton("적용 — 그래프·해석 값에 반영")
        theme.primary(apply_b)
        apply_b.clicked.connect(self.apply)
        clear_b = QPushButton("이 시료 처리 모두 해제")
        clear_b.clicked.connect(self.clear)
        v.addWidget(_row(apply_b, clear_b))

        g = QGroupBox("적분 (integ1) — 처리 후 데이터")
        gf = QFormLayout(g)
        self.ilo, self.ihi = QLineEdit(), QLineEdit()
        self.area = QComboBox()
        self.area.addItems(["수학적 면적", "절댓값 면적"])
        ib = QPushButton("적분")
        ib.clicked.connect(self.integrate)
        gf.addRow("X", _row(self.ilo, QLabel("~"), self.ihi))
        gf.addRow(_row(self.area, ib))
        v.addWidget(g)

        g = QGroupBox("보간 (interp1) — 주어진 X에서 Y")
        gf = QFormLayout(g)
        self.ixs = QLineEdit()
        self.ixs.setPlaceholderText("예: 0, 100, 500")
        self.imeth = QComboBox()
        self.imeth.addItems(["직선", "3차 스플라인"])
        pb = QPushButton("보간")
        pb.clicked.connect(self.interpolate)
        gf.addRow("X 값", self.ixs)
        gf.addRow(_row(self.imeth, pb))
        v.addWidget(g)
        v.addStretch(1)

        for w in (self.xmin, self.xmax):
            w.editingFinished.connect(self.preview)
        for w in (self.ref, self.sm):
            w.currentIndexChanged.connect(lambda _: self.preview())
        for w in (self.sm_n, self.sm_o):
            w.valueChanged.connect(lambda _: self.preview())
        self.common.toggled.connect(lambda _: self.preview())
        self._layout(c)

    # ---------------------------------------------------------------- 설정 ↔ 화면
    def _refs(self, it) -> list[dict]:
        return [r for r in self.mw.items if r is not it and r["kind"] == it["kind"]]

    def _target_changed(self):
        it = self.item()
        p = (it or {}).get("proc") or {}
        ws = (self.xmin, self.xmax, self.ref, self.common, self.sm, self.sm_n, self.sm_o)
        for w in ws:
            w.blockSignals(True)
        self.xmin.setText("" if p.get("xmin") is None else f"{p['xmin']:g}")
        self.xmax.setText("" if p.get("xmax") is None else f"{p['xmax']:g}")
        self.ref.clear()
        self.ref.addItem("없음")
        refs = self._refs(it) if it else []
        self.ref.addItems([r["name"] for r in refs])
        self.ref.setCurrentIndex(next((i + 1 for i, r in enumerate(refs) if r is p.get("ref")), 0))
        self.common.setChecked(bool(p.get("common_only")))
        self.sm.setCurrentIndex({"aav": 1, "sg": 2}.get(p.get("smooth"), 0))
        self.sm_n.setValue(int(p.get("smooth_n") or 5))
        self.sm_o.setValue(int(p.get("smooth_order") or 2))
        for w in ws:
            w.blockSignals(False)
        self._drop = set(p.get("drop", ()))
        self._cands = []
        self.cand.clear()
        self.preview()

    def settings(self) -> dict:
        """지금 화면 값 → 처리 설정 dict(기본값인 항목은 넣지 않음)."""
        it = self.item()
        p = {}
        if (lo := _num(self.xmin)) is not None:
            p["xmin"] = lo
        if (hi := _num(self.xmax)) is not None:
            p["xmax"] = hi
        if self._drop:
            p["drop"] = sorted(self._drop)
        refs = self._refs(it) if it else []
        if self.ref.currentIndex() > 0 and self.ref.currentIndex() - 1 < len(refs):
            p["ref"] = refs[self.ref.currentIndex() - 1]
            p["common_only"] = self.common.isChecked()
        if self.sm.currentIndex():
            p.update(smooth="aav" if self.sm.currentIndex() == 1 else "sg", smooth_n=self.sm_n.value(),
                     smooth_order=self.sm_o.value())
        return p

    def _processed(self, it, p):
        x, y, e = self.mw.raw_xy(it)
        ref = self.mw.raw_xy(p["ref"])[:2] if p.get("ref") is not None else None
        return proc_an.apply(x, y, e, p, ref)

    # ---------------------------------------------------------------- 동작
    def preview(self):
        it = self.item()
        self.drop_label.setText(f"뺀 점 {len(self._drop)}개")
        if it is None:
            self._draw(lambda fig: fig.add_subplot().text(0.5, 0.5, "열린 시료가 없습니다", ha="center"))
            return
        x, y, _ = self.mw.raw_xy(it)
        px, py, _ = self._processed(it, self.settings())
        xl, yl = self._labels(it)

        def draw(fig):
            ax = fig.add_subplot()
            ax.plot(x, y, color="0.75", lw=0.8, label="원본")
            ax.plot(px, py, color="C0", label="처리 후")
            d = [i for i in self._drop if i < x.size]
            if d:
                ax.plot(x[d], y[d], "x", color="C3", ms=7, label="뺀 점")
            c = [i for i in self._cands if i < x.size and i not in self._drop]
            if c:
                ax.plot(x[c], y[c], "o", mfc="none", color="C1", ms=8, label="튀는 점 후보")
            ax.set_xlabel(xl)
            ax.set_ylabel(yl)
            ax.set_title(it["name"])
            ax.legend()
        self._draw(draw)

    def find_spikes(self):
        it = self.item()
        if it is None:
            return
        _, y, _ = self.mw.raw_xy(it)
        x = self.mw.raw_xy(it)[0]
        self._cands = proc_an.find_spikes(y, self.win.value(), self.z.value())
        self.cand.clear()
        for i in self._cands:
            li = QListWidgetItem(f"#{i}  X={x[i]:.6g}  Y={y[i]:.6g}")
            li.setFlags(li.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            li.setCheckState(Qt.CheckState.Checked)
            li.setData(Qt.ItemDataRole.UserRole, i)
            self.cand.addItem(li)
        self.mw.status.setText(f"튀는 점 후보 {len(self._cands)}개 — 확인 후 「체크한 후보 빼기」, 「적용」")
        self.preview()

    def drop_checked(self):
        for k in range(self.cand.count()):
            li = self.cand.item(k)
            if li.checkState() == Qt.CheckState.Checked:
                self._drop.add(int(li.data(Qt.ItemDataRole.UserRole)))
        self.preview()

    def drop_range(self):
        it = self.item()
        lo, hi = _num(self.rlo), _num(self.rhi)
        if it is None or lo is None or hi is None:
            self.mw.status.setText("뺄 X 범위를 숫자로 넣으세요.")
            return
        x = self.mw.raw_xy(it)[0]
        self._drop |= {int(i) for i in np.flatnonzero((x >= min(lo, hi)) & (x <= max(lo, hi)))}
        self.preview()

    def undrop(self):
        self._drop = set()
        self.preview()

    def apply(self):
        it = self.item()
        if it is None:
            return
        p = self.settings()
        if p:
            it["proc"] = p
        else:
            it.pop("proc", None)
        it.pop("xrd_proc", None)
        if it["kind"] == "XRD" and p:
            x, y, _ = self._processed(it, p)
            try:  # XRD 판정·피크도 처리한 데이터로 다시(xrdcheck)
                it["xrd_proc"] = xrd_an.analyze(dataclasses.replace(it["data"], two_theta=x, counts=y))
            except Exception as e:
                QMessageBox.warning(self, "XRD 다시 해석 실패", f"그래프만 처리한 데이터로 그리고, 결과 표는 원본 해석입니다.\n{e}")
        self.mw.redraw()
        self.mw.status.setText(f"{it['name']}: 데이터 처리 — {proc_an.describe(p) if p else '해제'}")

    def clear(self):
        it = self.item()
        if it is None:
            return
        it.pop("proc", None)
        it.pop("xrd_proc", None)
        self._target_changed()
        self.mw.redraw()

    def integrate(self):
        it = self.item()
        if it is None:
            return
        x, y, _ = self.mw.xy(it)
        r = proc_an.integrate(x, y, _num(self.ilo), _num(self.ihi), self.area.currentIndex() == 1)
        _fill_table(self.table, ["항목", "값"], [["면적", r["area"]], ["최대 높이", r["y_max"]],
                                              ["최대 높이 X", r["x_at_max"]], ["반치폭", r["fwhm"]], ["점 수", r["n"]]])
        self.mw.status.setText("적분: 측정 순서대로 사다리꼴(루프면 둘러싼 면적 = 이력 손실)")

    def interpolate(self):
        it = self.item()
        if it is None:
            return
        try:
            xs = [float(t) for t in self.ixs.text().replace(";", ",").split(",") if t.strip()]
        except ValueError:
            self.mw.status.setText("X 값은 쉼표로 나눈 숫자로 넣으세요.")
            return
        x, y, _ = self.mw.xy(it)
        r = proc_an.interp_at(x, y, xs, "spline" if self.imeth.currentIndex() else "linear")
        _fill_table(self.table, ["X", *r], [[xv, *(float(v[i]) for v in r.values())] for i, xv in enumerate(xs)])


class PeakFitTab(_Tab):
    """구간 안 피크 여러 개 + 바탕선 동시 피팅(Origin fitpeaks·NLFit)."""

    def __init__(self, mw):
        super().__init__(mw)
        c = QWidget()
        f = QFormLayout(c)
        self.lo, self.hi = QLineEdit(), QLineEdit()
        self.lo.setPlaceholderText("처음부터")
        self.hi.setPlaceholderText("끝까지")
        self.kind = QComboBox()
        self.kind.addItems(list(fit_an.PEAKS))
        self.kind.setCurrentText("pseudo-Voigt")
        self.n = QSpinBox()
        self.n.setRange(1, 10)
        self.centers = QLineEdit()
        self.centers.setPlaceholderText("비우면 자동(두드러진 피크 순)")
        self.base = QComboBox()
        self.base.addItems(list(fit_an.BASELINES))
        self.base.setCurrentText("직선")
        go = QPushButton("피팅")
        theme.primary(go)
        go.clicked.connect(self.run)
        f.addRow("대상 시료", self.target)
        f.addRow("X 구간", _row(self.lo, QLabel("~"), self.hi))
        f.addRow("함수", self.kind)
        f.addRow("피크 수", self.n)
        f.addRow("피크 중심(쉼표)", self.centers)
        f.addRow("바탕선", self.base)
        f.addRow(go)
        f.addRow(_wrap("w = 반치폭(FWHM), 넓이 = 바탕선 위 적분.\n"
                        "XRD 판정·Scherrer 결정 크기는 그래프 탭 결과 표(xrdcheck) 값을 쓰세요."))
        self.result = None
        self._layout(c, "피팅 결과")

    def _target_changed(self):
        it = self.item()
        if it is not None:
            self._draw(lambda fig: self._plot_data(fig.add_subplot(), it))

    def _plot_data(self, ax, it):
        x, y, _ = self.mw.xy(it)
        ax.plot(x, y, color="0.4", lw=0.8)
        xl, yl = self._labels(it)
        ax.set_xlabel(xl)
        ax.set_ylabel(yl)
        ax.set_title(it["name"])

    def run(self) -> dict | None:
        it = self.item()
        if it is None:
            return None
        x, y, _ = self.mw.xy(it)
        lo, hi = _num(self.lo), _num(self.hi)
        sel = np.ones(x.size, bool)
        if lo is not None:
            sel &= x >= lo
        if hi is not None:
            sel &= x <= hi
        try:
            centers = [float(t) for t in self.centers.text().split(",") if t.strip()] or None
            r = fit_an.fit_peaks(x[sel], y[sel], self.kind.currentText(), centers, self.n.value(), self.base.currentText())
        except (ValueError, RuntimeError) as e:
            QMessageBox.warning(self, "피팅 실패", f"{e}\n구간을 좁히거나 피크 중심을 직접 넣어 보세요.")
            return None
        self.result = r
        xs, ys = x[sel], y[sel]
        o = np.argsort(xs)
        xs, ys = xs[o], ys[o]
        xf = np.linspace(xs[0], xs[-1], max(400, xs.size * 3))

        def draw(fig):
            ax, ar = fig.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [3, 1]})
            ax.plot(xs, ys, "o", ms=2.5, color="0.5", label="데이터")
            b = r["base_curve"](xf)
            for k, part in enumerate(r["parts"]):
                ax.fill_between(xf, b, b + part(xf), alpha=0.25, color=f"C{k + 1}", label=f"피크 {k + 1}")
            if r["base"]:
                ax.plot(xf, b, "--", color="0.3", lw=0.8, label="바탕선")
            ax.plot(xf, r["curve"](xf), color="C3", label=f"합(R²={r['r2']:.4f})")
            ax.legend(fontsize=8)
            ax.set_title(f"{it['name']} — {r['kind']}")
            ar.plot(xs, ys - r["curve"](xs), color="0.3", lw=0.8)
            ar.axhline(0, color="C3", lw=0.6)
            ar.set_ylabel("잔차")
            ar.set_xlabel(self._labels(it)[0])
        self._draw(draw)
        shape = next(iter(k for k in ("mu", "m") if k in r["peaks"][0]), None)
        heads = ["피크", "중심", "± 중심", "반치폭 w", "± w", "넓이", "± 넓이", "높이"] + ([shape, "± " + shape] if shape else [])
        rows = [[k + 1, p["xc"], p["xc_err"], p["w"], p["w_err"], p["area"], p["area_err"], p["height"]]
                + ([p[shape], p[shape + "_err"]] if shape else []) for k, p in enumerate(r["peaks"])]
        rows.append(["R²", r["r2"]] + [""] * (len(heads) - 2))
        _fill_table(self.table, heads, rows)
        self.mw.status.setText(f"피크 피팅 끝: {len(r['peaks'])}개, R² {r['r2']:.4f}")
        return r


class SatFitTab(_Tab):
    """VSM 루프에 랑주뱅 함수 또는 포화 접근 법칙 맞추기."""
    kinds = ("VSM",)
    MODELS = ("랑주뱅  M = Ms·L((H−H0)/a) + χH", "포화 접근 법칙  M = Ms(1 − a/H − b/H²) + χH")

    def __init__(self, mw):
        super().__init__(mw)
        c = QWidget()
        f = QFormLayout(c)
        self.model = QComboBox()
        self.model.addItems(self.MODELS)
        self.frac = QSpinBox()
        self.frac.setRange(5, 95)
        self.frac.setValue(50)
        self.frac.setSuffix(" %")
        self.frac.setToolTip("포화 접근 법칙: |H|가 H 최대의 이 비율 이상인 점만 맞춤")
        self.terms = {t: QCheckBox(lab) for t, lab in (("a", "a/H"), ("b", "b/H²"), ("chi", "χH"))}
        for t, box in self.terms.items():
            box.setChecked(t != "a")
        go = QPushButton("피팅")
        theme.primary(go)
        go.clicked.connect(self.run)
        f.addRow("대상 시료(VSM)", self.target)
        f.addRow("모델", self.model)
        f.addRow("고자장 맞춤 |H| ≥", self.frac)
        f.addRow("포화 접근 항", _row(*self.terms.values()))
        f.addRow(go)
        f.addRow(_wrap("랑주뱅: 초상자성·나노 입자. 이력은 무시하고 두 가지 평균에 맞춰집니다.\n"
                        "a = kT/(μ0·m) — 자기 모멘트 크기를 가늠.\n"
                        "포화 접근 법칙: 고자장 Ms 를 외삽(b 는 자기 이방성과 관련)."))
        self._layout(c, "피팅 결과")

    def _target_changed(self):
        it = self.item()
        if it is not None:
            h, m, _ = self.mw.xy(it)

            def draw(fig):
                ax = fig.add_subplot()
                ax.plot(h, m, color="0.4", lw=0.8)
                ax.set_xlabel(self._labels(it)[0])
                ax.set_ylabel(self._labels(it)[1])
                ax.set_title(it["name"])
            self._draw(draw)

    def run(self) -> dict | None:
        it = self.item()
        if it is None:
            return None
        h, m, _ = self.mw.xy(it)
        lang = self.model.currentIndex() == 0
        try:
            r = fit_an.fit_langevin(h, m) if lang else fit_an.fit_saturation(
                h, m, self.frac.value() / 100, [t for t, c in self.terms.items() if c.isChecked()])
        except (ValueError, RuntimeError) as e:
            QMessageBox.warning(self, "피팅 실패", str(e))
            return None
        hu, mu = it["data"].h_unit, it["data"].m_unit
        hf = np.linspace(-np.abs(h).max(), np.abs(h).max(), 800)

        def draw(fig):
            ax = fig.add_subplot()
            ax.plot(h, m, "o", ms=2, color="0.55", label="데이터")
            ax.plot(hf, r["curve"](hf), color="C3", label=f"피팅(R²={r['r2']:.4f})")
            ax.axhline(0, color="0.7", lw=0.5)
            ax.axvline(0, color="0.7", lw=0.5)
            ax.set_xlabel(self._labels(it)[0])
            ax.set_ylabel(self._labels(it)[1])
            ax.set_title(f"{it['name']} — {'랑주뱅' if lang else '포화 접근 법칙'}")
            ax.legend()
        self._draw(draw)
        units = {"Ms": mu, "a": hu, "H0": hu, "b": hu + "²", "chi": f"{mu}/{hu}"}
        names = ("Ms", "a", "H0", "chi") if lang else ("Ms", *r["terms"])
        rows = [[k if k != "chi" else "χ", units[k], r[k], r[k + "_err"]] for k in names]
        rows.append(["R²", "", r["r2"], None])
        if not lang:
            rows.append(["맞춘 점 수", "", r["n"], None])
        _fill_table(self.table, ["값", "단위", "피팅 값", "± 표준오차"], rows)
        msg = f"{'랑주뱅' if lang else '포화 접근'} 피팅 끝: Ms {r['Ms']:.5g} {mu}"
        e = r.get("Ms_err")
        if e is None or not np.isfinite(e) or e > 0.1 * abs(r["Ms"]):
            # 항끼리 겹치면 Ms 오차가 커짐 — 값만 보고 믿지 않게
            msg += "  ⚠ Ms 표준오차가 10 % 넘음: 항을 줄이거나 고자장 비율을 바꾸세요"
        self.mw.status.setText(msg)
        return r


class SheetTab(_Tab):
    """시료 데이터 표(Origin 워크시트): 원본·처리 후 보기, 복사·CSV, 식으로 새 시료(Set Column Values)."""

    def __init__(self, mw):
        super().__init__(mw)
        c = QWidget()
        f = QFormLayout(c)
        self.view = QComboBox()
        self.view.addItems(["처리 후(그래프와 같음)", "원본"])
        self.view.currentIndexChanged.connect(lambda _: self._target_changed())
        csv_b = QPushButton("CSV로 저장...")
        csv_b.clicked.connect(self.save_csv)
        self.formula = QLineEdit()
        self.formula.setPlaceholderText("예: y / 0.0123   ·   y * 1000   ·   np.log10(y)")
        self.formula.setToolTip("x, y(지금 보기의 값)와 np(numpy) 를 쓸 수 있습니다. 결과는 새 시료로 목록에 추가")
        make = theme.primary(QPushButton("새 Y 로 새 시료 만들기"))
        make.clicked.connect(self.make_sample)
        f.addRow("대상 시료", self.target)
        f.addRow("보기", self.view)
        f.addRow(csv_b)
        f.addRow(theme.section("열 계산 (Origin Set Column Values)"))
        f.addRow("새 Y =", self.formula)
        f.addRow(make)
        f.addRow(_wrap("만든 시료는 원본 파일이 없어 DB에 저장하지 않습니다(원본 결과를 덮지 않게)."))
        self._layout(c, "데이터")

    def _columns(self, it):
        x, y, e = (self.mw.raw_xy(it) if self.view.currentIndex() else self.mw.xy(it))
        xl, yl = self._labels(it)
        cols = [(xl, x), (yl, y)] + ([("오차", e)] if e is not None else [])
        return cols

    def _target_changed(self):
        it = self.item()
        if it is None:
            _fill_table(self.table, [], [])
            return
        cols = self._columns(it)
        _fill_table(self.table, [h for h, _ in cols], [list(map(float, r)) for r in zip(*(v for _, v in cols))])
        x, y = cols[0][1], cols[1][1]

        def draw(fig):
            ax = fig.add_subplot()
            ax.plot(x, y, lw=0.8)
            ax.set_xlabel(cols[0][0])
            ax.set_ylabel(cols[1][0])
            ax.set_title(it["name"])
        self._draw(draw)

    def save_csv(self, path: str | None = None):
        it = self.item()
        if it is None:
            return
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "CSV 저장", it["name"] + ".csv", "CSV (*.csv)")
        if not path:
            return
        cols = self._columns(it)
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:  # Excel 이 한글을 바로 읽게 BOM
                w = csv.writer(fh)
                w.writerow([h for h, _ in cols])
                w.writerows(zip(*(v for _, v in cols)))
        except OSError as e:
            QMessageBox.warning(self, "CSV 저장 실패", str(e))
            return
        self.mw.status.setText(f"CSV 저장: {path}")

    def make_sample(self) -> dict | None:
        it = self.item()
        expr = self.formula.text().strip()
        if it is None or not expr:
            return None
        cols = self._columns(it)
        x, y = np.asarray(cols[0][1], float), np.asarray(cols[1][1], float)
        try:  # 이 PC 사용자가 직접 넣는 식 — 이름 공간을 x·y·numpy 로만 제한
            new = np.asarray(eval(expr, {"__builtins__": {}}, {"x": x, "y": y, "np": np}), float)  # noqa: S307
            new = np.broadcast_to(new, y.shape).copy()
        except Exception as e:
            QMessageBox.warning(self, "식 오류", f"{expr}\n{e}")
            return None
        d = it["data"]
        name = f"{it['name']} [{expr}]"
        if it["kind"] == "VSM":
            data = dataclasses.replace(d, h=x, m=new, m_err=None, device={}, sample_id=name)
            item = {"kind": "VSM", "name": name, "data": data, "derived": True}
        else:
            data = dataclasses.replace(d, two_theta=x, counts=new, sample_name=name)
            item = {"kind": "XRD", "name": name, "data": data, "derived": True}
            try:
                item["xrd_result"] = xrd_an.analyze(data)
            except Exception as e:
                QMessageBox.warning(self, "XRD 해석 실패", f"새 시료를 만들 수 없습니다.\n{e}")
                return None
        self.mw.items.append(item)
        self.mw._fill_list()
        self.refresh()
        self.mw.status.setText(f"새 시료: {name}")
        return item
