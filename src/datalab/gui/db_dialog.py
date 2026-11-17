"""DB 목록 보기·태깅 창: 시료 정보(조성·공정·로트·메모·태그) 편집, 저장해 둔 원본을 다시 열기."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout)

from datalab import db

SAMPLE_COLS = (("name", "시료"), ("composition", "조성"), ("process", "공정"), ("lot", "로트"),
               ("memo", "메모"), ("tags", "태그(쉼표로 구분)"), ("n", "측정 수"))
EDITABLE = (*db.Store.SAMPLE_FIELDS, "tags")


class DbDialog(QDialog):
    def __init__(self, main, root):
        super().__init__(main)
        self.main = main
        self.store = db.Store(root)
        self.finished.connect(self.store.close)
        self.setWindowTitle("DB 목록·태깅")
        self.resize(900, 600)

        self.search = QLineEdit()
        self.search.setPlaceholderText("검색: 이름·조성·공정·로트·메모·태그·파일 이름 (띄어쓰기 = 모두 포함)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._fill_samples)
        self.kind = QComboBox()
        self.kind.addItems(["전체", "VSM", "XRD"])
        self.kind.currentTextChanged.connect(self._fill_samples)
        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(QLabel("종류"))
        top.addWidget(self.kind)

        self.samples = QTableWidget(0, len(SAMPLE_COLS))
        self.samples.setHorizontalHeaderLabels([t for _, t in SAMPLE_COLS])
        self.samples.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.samples.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.samples.horizontalHeader().setStretchLastSection(True)
        self.meas = QTableWidget(0, 4)
        self.meas.setHorizontalHeaderLabels(["종류", "원본 파일 이름", "측정일", "DB 저장일"])
        self.meas.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.meas.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.meas.horizontalHeader().setStretchLastSection(True)
        self.meas.cellDoubleClicked.connect(lambda *_: self.open_selected())

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.samples)
        split.addWidget(self.meas)
        open_btn = QPushButton("선택 측정 열기")
        open_btn.clicked.connect(self.open_selected)
        cmp_btn = QPushButton("결과 비교표...")
        cmp_btn.setToolTip("지금 목록에 보이는 시료(검색·종류 적용)의 측정 결과를 한 표로 — 열 머리를 눌러 정렬, Excel 저장")
        cmp_btn.clicked.connect(self.compare)
        self.info = QLabel("칸을 더블클릭해 고치면 바로 저장됩니다. 측정을 고르지 않고 열면 그 시료 측정 전부를 엽니다.")
        bottom = QHBoxLayout()
        bottom.addWidget(self.info, 1)
        bak_btn = QPushButton("NAS로 백업...")
        bak_btn.setToolTip("고른 폴더의 DataLab_Backup 에 날짜별 DB 사본과 원본(없는 것만)을 저장")
        bak_btn.clicked.connect(lambda: self.backup())
        mrg_btn = QPushButton("백업 가져오기(병합)...")
        mrg_btn.setToolTip("다른 PC 백업의 datalab_*.sqlite 를 골라 합침 — 같은 원본 파일은 한 번만")
        mrg_btn.clicked.connect(lambda: self.merge())
        bottom.addWidget(bak_btn)
        bottom.addWidget(mrg_btn)
        bottom.addWidget(cmp_btn)
        bottom.addWidget(open_btn)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(split)
        lay.addLayout(bottom)

        self.samples.itemChanged.connect(self._edited)
        self.samples.itemSelectionChanged.connect(self._fill_meas)
        self._fill_samples()

    def _fill_samples(self):
        self.samples.blockSignals(True)
        kind = self.kind.currentText()
        rows = self.store.samples(self.search.text(), None if kind == "전체" else kind)
        self._ids = [s["id"] for s in rows]
        self.samples.setRowCount(len(rows))
        for r, s in enumerate(rows):
            for c, (key, _) in enumerate(SAMPLE_COLS):
                it = QTableWidgetItem("" if s[key] is None else str(s[key]))
                it.setData(Qt.ItemDataRole.UserRole, s["id"])
                if key not in EDITABLE:  # 이름은 같은 시료 묶음 기준이라 여기서 바꾸지 않음
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.samples.setItem(r, c, it)
        self.samples.blockSignals(False)
        self.samples.resizeColumnsToContents()
        if rows:
            self.samples.selectRow(0)
        self._fill_meas()  # 결과가 없으면 측정 목록도 비움

    def _edited(self, it: QTableWidgetItem):
        key = SAMPLE_COLS[it.column()][0]
        self.store.update_sample(it.data(Qt.ItemDataRole.UserRole), key, it.text())
        self.info.setText(f"저장함: {self.samples.item(it.row(), 0).text()} · {SAMPLE_COLS[it.column()][1]}")

    def _sample_id(self) -> int | None:
        rows = self.samples.selectionModel().selectedRows()
        return self.samples.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole) if rows else None

    def _fill_meas(self):
        sid = self._sample_id()
        self._meas = self.store.measurements(sid) if sid is not None else []
        self.meas.setRowCount(len(self._meas))
        for r, m in enumerate(self._meas):
            for c, key in enumerate(("kind", "file_name", "measured_at", "created_at")):
                self.meas.setItem(r, c, QTableWidgetItem(m[key] or ""))
        self.meas.resizeColumnsToContents()

    def open_selected(self) -> int:
        """고른 측정(없으면 그 시료 전부)의 원본 사본을 본 창에 연다. 이름은 DB 시료 이름. 돌려줌: 연 파일 수."""
        rows = sorted({i.row() for i in self.meas.selectedIndexes()}) or range(len(self._meas))
        ms = [self._meas[r] for r in rows]
        if not ms:
            return 0
        name = self.samples.item(self.samples.selectionModel().selectedRows()[0].row(), 0).text()
        self.main.open_paths([str(m["path"]) for m in ms], names={str(m["path"]): name for m in ms})
        return len(ms)

    def compare(self) -> "CompareDialog":
        kind = self.kind.currentText()
        heads, rows = self.store.compare(self._ids, None if kind == "전체" else kind)
        self._cmp = CompareDialog(self, heads, rows)
        self._cmp.show()
        return self._cmp

    # shortcut: 백업 폴더를 기억하지 않음(매번 고름), 자주 쓰면 %APPDATA%\datalab 설정에 저장
    def backup(self, folder: str | None = None) -> bool:
        if folder is None:
            folder = QFileDialog.getExistingDirectory(self, "백업할 폴더(NAS) 고르기")
            if not folder:
                return False
        try:
            path = self.store.backup(folder)
        except OSError as e:
            QMessageBox.warning(self, "백업 실패", str(e))
            return False
        self.info.setText(f"백업함: {path}")
        return True

    def merge(self, path: str | None = None) -> dict | None:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "합칠 백업 DB 고르기", "", "DataLab DB (*.sqlite)")
            if not path:
                return None
        try:
            r = self.store.merge(path)
        except (OSError, sqlite3.Error) as e:
            QMessageBox.warning(self, "병합 실패", f"{e}\n\n이 PC의 DB는 바뀌지 않았습니다.")
            return None
        self._fill_samples()
        self.info.setText(f"병합: 새 시료 {r['samples']}개 · 새 측정 {r['measurements']}개 · "
                          f"이미 있던 측정 {r['skipped']}개 건너뜀")
        return r


class CompareDialog(QDialog):
    """결과 비교표: 측정 한 줄씩. 열 머리를 누르면 정렬(숫자는 숫자 크기로), Excel 저장."""

    def __init__(self, parent, heads: list[str], rows: list[list]):
        super().__init__(parent)
        self.heads, self.rows = heads, rows
        self.setWindowTitle(f"결과 비교표 — 측정 {len(rows)}개")
        self.resize(1100, 500)
        self.table = QTableWidget(len(rows), len(heads))
        self.table.setHorizontalHeaderLabels(heads)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for r, row in enumerate(rows):
            for c, v in enumerate(row):
                it = QTableWidgetItem()
                if isinstance(v, (int, float)):
                    it.setData(Qt.ItemDataRole.DisplayRole, v)  # 숫자로 넣어야 정렬이 크기 순
                else:
                    it.setText("" if v is None else str(v))
                self.table.setItem(r, c, it)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        save = QPushButton("Excel로 저장...")
        save.clicked.connect(lambda: self.save_xlsx())
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("열 머리를 누르면 정렬합니다. Excel에는 DB 값 그대로(정렬 전 순서) 저장합니다."), 1)
        bottom.addWidget(save)
        lay = QVBoxLayout(self)
        lay.addWidget(self.table)
        lay.addLayout(bottom)

    def save_xlsx(self, path: str | None = None) -> bool:
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Excel로 저장", str(db.DATA_DIR / "결과비교.xlsx"),
                                                  "Excel (*.xlsx)")
            if not path:
                return False
        try:
            db.write_xlsx(path, self.heads, self.rows)
        except OSError as e:  # Excel에서 열어 둔 파일이면 PermissionError
            QMessageBox.warning(self, "저장 실패", f"{e}\n\nExcel에서 열려 있으면 닫고 다시 저장하세요.")
            return False
        return True
