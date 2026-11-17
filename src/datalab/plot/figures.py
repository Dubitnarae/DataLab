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
    # 목록을 font.family에 직접 둬야 글자별로 다음 글꼴로 넘어감("sans-serif"로 두면 Arial 하나만 써서 한글이 깨짐)
    "font.family": ["Arial", "Malgun Gothic", "DejaVu Sans"],
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


LEGEND_LOC = {"자동": None, "숨김": None, "가장 빈 곳": "best", "오른쪽 위": "upper right", "왼쪽 위": "upper left",
              "오른쪽 아래": "lower right", "왼쪽 아래": "lower left", "그래프 밖 오른쪽": "upper left"}
MARKERS = {"없음": "", "○": "o", "□": "s", "△": "^", "◇": "D", "×": "x", "+": "+"}


def _plot(ax, name, x, y, kw: dict):
    """kw: 편집 패널의 선 모양(color·lw·marker). 빈 값은 프리셋 기본."""
    kw = {k: v for k, v in kw.items() if v}
    if kw.get("marker"):
        # shortcut: 기호를 약 40개만 찍음(수천 점 루프가 굵은 띠가 되지 않게), 간격 지정 요청 오면 옵션으로
        kw.update(markevery=max(1, len(x) // 40), markerfacecolor="none")
    ax.plot(x, y, label=name, **kw)


def apply_axes(ax, o: dict) -> None:
    """편집 패널 값: {x,y}{min,max,step,log,title}, legend. None·0·빈 문자열은 자동(프리셋 그대로)."""
    from matplotlib.ticker import MultipleLocator

    for a in "xy":
        if o.get(f"{a}log"):
            getattr(ax, f"set_{a}scale")("log")
        lo, hi = o.get(f"{a}min"), o.get(f"{a}max")
        if lo is not None or hi is not None:
            getattr(ax, f"set_{a}lim")(lo, hi)
        if o.get(f"{a}step") and not o.get(f"{a}log"):
            getattr(ax, f"{a}axis").set_major_locator(MultipleLocator(o[f"{a}step"]))
        if o.get(f"{a}title"):
            getattr(ax, f"set_{a}label")(o[f"{a}title"])  # $...$ 안은 mathtext(위첨자·그리스 문자)
    leg = o.get("legend") or "자동"
    if leg == "숨김":
        if ax.get_legend():
            ax.get_legend().remove()
    elif leg == "그래프 밖 오른쪽":
        ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1))
    elif leg != "자동":
        ax.legend(loc=LEGEND_LOC[leg])


def draw_vsm(fig: Figure, items: list[tuple[str, np.ndarray, np.ndarray, dict]], h_label: str, m_label: str,
             inset: bool = True, inset_half_width: float | None = None) -> None:
    """items: (표시명, H, M, 선 모양). inset이면 원점 부근 확대(연자성 루프는 전체에서 Hc가 안 보임)."""
    ax = fig.add_subplot()
    for name, h, m, kw in items:
        _plot(ax, name, h, m, kw)
    ax.axhline(0, color="0.6", lw=0.5, zorder=0)
    ax.axvline(0, color="0.6", lw=0.5, zorder=0)
    ax.set_xlabel(h_label)
    ax.set_ylabel(m_label)
    if len(items) > 1:
        ax.legend()
    if inset and items:
        hmax = max(float(np.abs(h).max()) for _, h, _, _ in items)
        w = inset_half_width or hmax * 0.02
        ins = ax.inset_axes([0.58, 0.08, 0.38, 0.38])
        for line, (_, h, m, _) in zip(ax.get_lines(), items):
            ins.plot(h, m, color=line.get_color(), lw=line.get_linewidth() * 0.8)
        near = np.concatenate([m[np.abs(h) <= w] for _, h, m, _ in items]) if items else np.array([])
        ins.set_xlim(-w, w)
        if near.size:
            mm = float(np.abs(near).max()) * 1.1 or 1.0
            ins.set_ylim(-mm, mm)
        ins.axhline(0, color="0.6", lw=0.4)
        ins.axvline(0, color="0.6", lw=0.4)
        ins.tick_params(labelsize="x-small")


def draw_xrd(fig: Figure, items: list[tuple[str, np.ndarray, np.ndarray, dict]], offset: float = 0.0,
             normalize: bool = True) -> None:
    """items: (표시명, 2θ, counts, 선 모양). offset>0이면 세로로 띄워 그린다(waterfall, 정규화 높이 기준)."""
    ax = fig.add_subplot()
    for k, (name, x, y, kw) in enumerate(items):
        y = y / y.max() if normalize and y.max() > 0 else y
        _plot(ax, name, x, y + k * offset * (1 if normalize else float(y.max())), kw)
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
