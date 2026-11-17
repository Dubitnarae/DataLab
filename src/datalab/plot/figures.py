"""논문·PPT용 그래프. 화면과 저장이 같은 Figure를 쓴다(크기도 프리셋 그대로).

스타일 프리셋 3종(PLAN 1장): PPT용, 논문 1단(8.5 cm), 논문 2단(17.5 cm). 안쪽 눈금·네 변 눈금(Origin 기본과 같음).
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

CM = 1 / 2.54
_BASE = {
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Malgun Gothic", "DejaVu Sans"],  # 한글 시료명은 맑은 고딕으로
    "axes.unicode_minus": False,
    "xtick.direction": "in", "ytick.direction": "in",
    "xtick.top": True, "ytick.right": True,
    "xtick.minor.visible": True, "ytick.minor.visible": True,
    "legend.frameon": False,
}
STYLES = {
    "PPT용": {"size": (16 * CM, 12 * CM), "rc": {"font.size": 16, "lines.linewidth": 2.5, "axes.linewidth": 1.5,
                                                 "xtick.major.width": 1.5, "ytick.major.width": 1.5,
                                                 "xtick.major.size": 6, "ytick.major.size": 6}},
    "논문 1단": {"size": (8.5 * CM, 6.5 * CM), "rc": {"font.size": 8, "lines.linewidth": 1.0, "axes.linewidth": 0.8,
                                                   "xtick.major.size": 3.5, "ytick.major.size": 3.5}},
    "논문 2단": {"size": (17.5 * CM, 9 * CM), "rc": {"font.size": 9, "lines.linewidth": 1.2, "axes.linewidth": 0.8,
                                                   "xtick.major.size": 4, "ytick.major.size": 4}},
}
DPI = {".png": 600, ".tif": 600, ".tiff": 600}


def apply_style(style: str) -> None:
    """전역 rcParams를 프리셋으로 바꾼다. 눈금은 그릴 때 늦게 만들어지므로 rc_context로는 부족하다."""
    import matplotlib

    matplotlib.rcdefaults()
    matplotlib.rcParams.update({**_BASE, **STYLES[style]["rc"]})


def new_figure(style: str) -> Figure:
    return Figure(figsize=STYLES[style]["size"], dpi=100, layout="constrained")


def draw_vsm(fig: Figure, items: list[tuple[str, np.ndarray, np.ndarray]], h_label: str, m_label: str,
             inset: bool = True, inset_half_width: float | None = None) -> None:
    """items: (표시명, H, M). inset이면 원점 부근 확대(연자성 루프는 전체에서 Hc가 안 보임)."""
    ax = fig.add_subplot()
    for name, h, m in items:
        ax.plot(h, m, label=name)
    ax.axhline(0, color="0.6", lw=0.5, zorder=0)
    ax.axvline(0, color="0.6", lw=0.5, zorder=0)
    ax.set_xlabel(h_label)
    ax.set_ylabel(m_label)
    if len(items) > 1:
        ax.legend()
    if inset and items:
        hmax = max(float(np.abs(h).max()) for _, h, _ in items)
        w = inset_half_width or hmax * 0.02
        ins = ax.inset_axes([0.58, 0.08, 0.38, 0.38])
        for line, (_, h, m) in zip(ax.get_lines(), items):
            ins.plot(h, m, color=line.get_color(), lw=line.get_linewidth() * 0.8)
        near = np.concatenate([m[np.abs(h) <= w] for _, h, m in items]) if items else np.array([])
        ins.set_xlim(-w, w)
        if near.size:
            mm = float(np.abs(near).max()) * 1.1 or 1.0
            ins.set_ylim(-mm, mm)
        ins.axhline(0, color="0.6", lw=0.4)
        ins.axvline(0, color="0.6", lw=0.4)
        ins.tick_params(labelsize="x-small")


def draw_xrd(fig: Figure, items: list[tuple[str, np.ndarray, np.ndarray]], offset: float = 0.0,
             normalize: bool = True) -> None:
    """items: (표시명, 2θ, counts). offset>0이면 세로로 띄워 그린다(waterfall, 정규화 높이 기준)."""
    ax = fig.add_subplot()
    for k, (name, x, y) in enumerate(items):
        y = y / y.max() if normalize and y.max() > 0 else y
        ax.plot(x, y + k * offset * (1 if normalize else float(y.max())), label=name)
    ax.set_xlabel("2θ (°)")
    ax.set_ylabel("Intensity (a.u.)" if normalize else "Intensity (counts)")
    if normalize:
        ax.set_yticklabels([])
    if len(items) > 1:
        ax.legend()


def save(fig: Figure, path: str | Path) -> Path:
    """PNG·TIF 600 dpi, SVG·PDF 벡터."""
    path = Path(path)
    fig.savefig(path, dpi=DPI.get(path.suffix.lower(), 600))
    return path


def png_bytes(fig: Figure, dpi: int = 300) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    return buf.getvalue()
