"""VSM(M-H 루프) 파일 읽기.

- Lake Shore 8600 csv: `#RUN ON SOFTWARE`로 시작. `#EXTRACTED PARAMETERS`에 장비 계산값, `Step,...` 줄 아래 측정점 표.
- 옛 IDEAS VSM txt: `Start Time:`으로 시작, `***DATA***` 아래 H·M 두 열.
- 그 밖: 숫자 2열 이상 텍스트(첫 열 H, 둘째 열 M). 머리줄의 `(Oe)`·`[emu/g]`에서 단위를 읽는다.
형식 근거: AI 오피스 server/src/analysis/vsm.ts (실측 csv 3,082개로 확인, 2026-11).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


class UnsupportedVsmFile(ValueError):
    pass


@dataclass
class VsmData:
    path: Path
    sample_id: str
    h: np.ndarray = field(repr=False)
    m: np.ndarray = field(repr=False)
    h_unit: str = "Oe"
    m_unit: str = "emu/g"
    file_format: str = ""  # "lakeshore_csv" | "ideas_txt" | "generic"
    device: dict = field(default_factory=dict)  # 장비가 계산한 Hc·Mr·Ms(절댓값)
    meta: dict = field(default_factory=dict)


_NUM = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$")
_UNIT = re.compile(r"[\[(]([^\])]+)[\])]")


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1")


def _lakeshore(lines: list[str]) -> tuple[list, list, str, str, dict, dict]:
    h, m, device, meta = [], [], {}, {}
    hi = mi = -1
    section, sid, m_unit = "", "", "emu/g"
    for line in lines:
        if line.startswith("#"):
            section = line.strip()
            continue
        if hi >= 0:
            c = line.split(",")
            try:
                h.append(float(c[hi]))
                m.append(float(c[mi]))
            except (IndexError, ValueError):
                pass
            continue
        if section == "#SAMPLE SETTINGS":
            if line.startswith("ID:"):
                sid = line[3:].strip()
            elif mm := re.match(r"Mass:\s*([-+\d.Ee]+)\s*g", line):
                meta["mass_g"] = float(mm.group(1))
        if section == "#EXTRACTED PARAMETERS":
            if p := re.match(r"^\s*([^:]+?)\s*:\s*(-?[\d.]+(?:E[-+]?\d+)?)", line, re.I):
                name, v = p.group(1).lower(), abs(float(p.group(2)))
                if "coercivity" in name:
                    device["Hc"] = v
                elif name.startswith("remanent"):
                    device["Mr"] = v
                elif name.startswith("saturation"):
                    device["Ms"] = v
        if line.startswith("Step,"):
            cols = line.split(",")
            hi = next((i for i, c in enumerate(cols) if c.startswith("Field [")), -1)
            if hi < 0:
                raise UnsupportedVsmFile("Lake Shore 표에 Field 열이 없습니다.")
            mi = hi + 1
            if u := re.search(r"\[([^\]]+)\]", cols[mi] if mi < len(cols) else ""):  # "(M) [emu/g]"의 [ ]
                m_unit = u.group(1)
    return h, m, sid, m_unit, device, meta


def _columns(lines: list[str]) -> tuple[list, list, str, str]:
    """숫자 줄에서 앞 두 열. 숫자 줄 바로 앞 글 줄을 머리줄로 보고 단위를 읽는다."""
    h, m, header = [], [], ""
    for line in lines:
        c = [t for t in re.split(r"[,\t;]|\s+", line.strip()) if t]
        if len(c) >= 2 and _NUM.match(c[0]) and _NUM.match(c[1]):
            h.append(float(c[0]))
            m.append(float(c[1]))
        elif not h and line.strip():
            header = line
    units = _UNIT.findall(header)
    return h, m, units[0] if units else "Oe", units[1] if len(units) > 1 else ""


def read_vsm(path: str | Path, allow_generic: bool = True) -> VsmData:
    path = Path(path)
    text = _read_text(path)
    lines = text.splitlines()
    device, meta, sid = {}, {}, ""
    if text.startswith("#RUN ON SOFTWARE"):
        fmt = "lakeshore_csv"
        h, m, sid, m_unit, device, meta = _lakeshore(lines)
        h_unit = "Oe"
    elif text.startswith("Start Time:") and "***DATA***" in text:
        fmt = "ideas_txt"
        if s := re.search(r"^Sample ID:\s*(.+)$", text, re.M):
            sid = s.group(1).strip()
        start = next(i for i, ln in enumerate(lines) if "***DATA***" in ln)
        h, m, h_unit, m_unit = _columns(lines[start + 1:])
        m_unit = m_unit or "emu/g"
    elif allow_generic:
        fmt = "generic"
        h, m, h_unit, m_unit = _columns(lines)
    else:
        raise UnsupportedVsmFile(f"VSM 파일 형식이 아닙니다: {path.name}")
    if len(h) < 10:
        raise UnsupportedVsmFile(f"측정점이 10개 미만입니다: {path.name}")
    return VsmData(path, sid or path.stem, np.asarray(h, float), np.asarray(m, float),
                   h_unit, m_unit, fmt, device, meta)
