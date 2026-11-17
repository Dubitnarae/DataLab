"""DB 목록 보기·태깅 창: 시료 정보(조성·공정·로트·메모·태그) 편집, 저장해 둔 원본을 다시 열기."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QLabel, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

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
        self.info = QLabel("칸을 더블클릭해 고치면 바로 저장됩니다. 측정을 고르지 않고 열면 그 시료 측정 전부를 엽니다.")
        bottom = QHBoxLayout()
        bottom.addWidget(self.info, 1)
        bottom.addWidget(open_btn)
        lay = QVBoxLayout(self)
        lay.addWidget(split)
        lay.addLayout(bottom)

        self.samples.itemChanged.connect(self._edited)
        self.samples.itemSelectionChanged.connect(self._fill_meas)
        self._fill_samples()

    def _fill_samples(self):
        self.samples.blockSignals(True)
        rows = self.store.samples()
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
