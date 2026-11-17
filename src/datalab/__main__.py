"""`python -m datalab [gui] [파일 ...]` — GUI를 띄운다."""

import sys

if __name__ == "__main__":
    from datalab.gui.app import run

    args = sys.argv[1:]
    sys.exit(run(args[1:] if args[:1] == ["gui"] else args))
