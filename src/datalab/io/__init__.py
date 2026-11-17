"""파일 하나를 열어 종류(VSM/XRD)를 정한다."""

from __future__ import annotations

from pathlib import Path

from datalab.io.vsm import UnsupportedVsmFile, VsmData, read_vsm

__all__ = ["load_any", "VsmData", "UnsupportedVsmFile", "read_vsm"]


def load_any(path: str | Path) -> tuple[str, object]:
    """("VSM", VsmData) 또는 ("XRD", xrdcheck Pattern). 둘 다 아니면 ValueError.

    순서: VSM 장비 형식 → XRD 전용 형식(.xrdml·.rasx) → XRD 읽기 → H에 음수가 있는 숫자 2열(VSM).
    """
    from xrdcheck.io import load_pattern

    path = Path(path)
    try:
        return "VSM", read_vsm(path, allow_generic=False)
    except UnsupportedVsmFile:
        pass
    xrd_err = None
    try:
        p = load_pattern(path)
        if p.two_theta.min() >= 0:
            return "XRD", p
    except Exception as e:  # xrdcheck가 내는 여러 읽기 오류
        xrd_err = e
    try:
        d = read_vsm(path)
        if d.h.min() < 0:
            return "VSM", d
    except UnsupportedVsmFile:
        pass
    raise ValueError(f"VSM·XRD 파일로 읽을 수 없습니다: {path.name}" + (f" ({xrd_err})" if xrd_err else ""))
