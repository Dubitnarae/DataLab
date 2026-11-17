"""GUI 실행: `python -m datalab gui [파일|폴더 ...]`."""

from __future__ import annotations

import sys


def run(paths: list[str] | None = None) -> int:
    from importlib import resources

    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication

    from datalab import updater
    from datalab.gui.main_window import APP_TITLE, MainWindow

    updater.cleanup()  # 지난 업데이트의 임시·백업 폴더

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setFont(QFont("Malgun Gothic", 9))
    icon = resources.files("datalab").joinpath("data/icon.ico")
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    w = MainWindow()
    w.show()
    if paths:
        w.open_paths(paths)
    return app.exec()
