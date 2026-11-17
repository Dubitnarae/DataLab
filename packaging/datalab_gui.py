"""PyInstaller 진입점: exe를 실행하면 GUI를 띄운다. exe에 파일·폴더를 끌어다 놓으면 그것을 연다."""

import sys

if __name__ == "__main__":
    from datalab.gui.app import run

    sys.exit(run(sys.argv[1:]))
