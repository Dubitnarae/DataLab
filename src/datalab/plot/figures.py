"""논문·PPT용 그래프. 화면과 저장이 같은 Figure를 쓴다(크기도 프리셋 그대로).

스타일 프리셋 3종(PLAN 1장): PPT용, 논문 1단(8.5 cm), 논문 2단(17.5 cm). 안쪽 눈금·네 변 눈금(Origin 기본과 같음).
여기에 글꼴 선택과 흑백 출판(검정 + 실선·파선·점선·일점쇄선)을 겹쳐 쓴다.
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


FONTS = ["Arial", "Times New Roman", "Calibri", "Malgun Gothic"]
# 흑백 출판: 색 대신 선 모양으로 구분(실선·파선·점선·일점쇄선·이점쇄선·긴 파선·촘촘한 점선)
BW_LS = ["-", "--", ":", "-.", (0, (5, 1.5, 1, 1.5, 1, 1.5)), (0, (10, 3)), (0, (1, 1))]


def apply_style(style: str, font: str = "Arial", bw: bool = False) -> None:
    """전역 rcParams를 프리셋으로 바꾼다. 눈금은 그릴 때 늦게 만들어지므로 rc_context로는 부족하다.
    font는 글꼴 목록 맨 앞(없는 글자는 맑은 고딕으로 넘어감), bw면 선 색을 모두 검정(C0~C9 → k)."""
    import matplotlib
    from cycler import cycler

    matplotlib.rcdefaults()
    rc = {**_BASE, **STYLES[style]["rc"], "font.family": [font, *[f for f in _BASE["font.family"] if f != font]]}
    if font == "Times New Roman":
        rc["mathtext.fontset"] = "stix"  # 수식 글자도 Times 모양으로
    if bw:
        rc["axes.prop_cycle"] = cycler(color=["k"], linestyle=BW_LS[:1])
    matplotlib.rcParams.update(rc)


def new_figure(style: str) -> Figure:
    return Figure(figsize=STYLES[style]["size"], dpi=100, layout="constrained")


LEGEND_LOC = {"자동": None, "숨김": None, "가장 빈 곳": "best", "오른쪽 위": "upper right", "왼쪽 위": "upper left",
              "오른쪽 아래": "lower right", "왼쪽 아래": "lower left", "그래프 밖 오른쪽": "upper left"}
MARKERS = {"없음": "", "○": "o", "□": "s", "△": "^", "◇": "D", "×": "x", "+": "+"}


STACK = "세로 쌓기(시료마다 한 칸)"
LAYOUTS = {"한 그래프": (1, 1), "세로 2패널": (2, 1), "가로 2패널": (1, 2), "4패널(2×2)": (2, 2), "9패널(3×3)": (3, 3),
           STACK: None}
_NOT_PLOT = ("panel", "right", "err")  # 시료 style 중 선 모양이 아닌 값(배치·오차 막대)


def _panels(fig: Figure, items: list, layout: str) -> tuple[list, list]:
    """(패널 축 목록, 시료별 그릴 축). style의 panel(1부터, 0=차례대로 돌려 배치), right=그 패널 오른쪽 Y축(Double-Y)."""
    if layout == STACK:  # Origin Stack: X 공유, 패널 사이 틈 없음, 위쪽 패널은 X 눈금 글자 숨김
        panels = list(np.ravel(fig.subplots(max(1, min(len(items), 9)), 1, sharex=True, squeeze=False)))
        fig.get_layout_engine().set(h_pad=0, hspace=0)
        for p in panels[:-1]:
            p.tick_params(labelbottom=False)
    else:
        r, c = LAYOUTS[layout]
        panels = list(np.ravel(fig.subplots(r, c, squeeze=False)))
    twins, axs = {}, []
    for k, (*_, kw) in enumerate(items):
        p = min(kw.get("panel") or k % len(panels) + 1, len(panels)) - 1
        ax = panels[p]
        if kw.get("right"):
            if p not in twins:
                twins[p] = ax.twinx()
                twins[p].dl_parent = ax  # 세로 쌓기는 패널끼리도 X를 공유해서 공유 여부로는 오른쪽 Y축을 못 가림
            ax = twins[p]
        axs.append(ax)
    return panels, axs


def _siblings(ax) -> list:
    """패널 축과 그 오른쪽 Y축."""
    return [ax] + [a for a in ax.figure.axes if getattr(a, "dl_parent", None) is ax]


def _legend(ax, min_n: int = 1, rev: bool = False, **kw) -> None:
    """왼쪽·오른쪽 Y축 선을 범례 하나로. 맨 위 축에 둬야 오른쪽 선에 가리지 않는다. rev: 범례 순서 뒤집기."""
    sibs = _siblings(ax)
    for a in sibs:
        if a.get_legend():
            a.get_legend().remove()
    h, lab = [], []
    for a in sibs:
        hh, ll = a.get_legend_handles_labels()
        h, lab = h + hh, lab + ll
    if rev:
        h, lab = h[::-1], lab[::-1]
    if len(h) >= min_n:
        sibs[-1].legend(h, lab, **kw)


def _plot(ax, name, x, y, kw: dict, k: int):
    """kw: 편집 패널의 선 모양(color·lw·marker). 빈 값은 프리셋 기본, 색은 시료 순서(C0, C1…)로 고정 — 오른쪽 Y축도 같은 순서.
    kw["err"]: Y 오차(배열)면 오차 막대(Origin Y Error)."""
    import matplotlib

    bw = matplotlib.rcParams["axes.prop_cycle"].by_key().get("linestyle")  # apply_style(bw=True)일 때만 있음
    err = kw.get("err")
    kw = {"color": f"C{k % 10}", **({"ls": BW_LS[k % len(BW_LS)]} if bw else {}),
          **{a: v for a, v in kw.items() if a not in _NOT_PLOT and v}}
    every = max(1, len(x) // 40)
    if kw.get("marker"):
        # shortcut: 기호를 약 40개만 찍음(수천 점 루프가 굵은 띠가 되지 않게), 간격 지정 요청 오면 옵션으로
        kw.update(markevery=every, markerfacecolor="none")
    if err is not None:  # 막대도 약 40개만(촘촘하면 띠가 됨)
        return ax.errorbar(x, y, yerr=err, errorevery=every, capsize=2, elinewidth=0.6, label=name, **kw).lines[0]
    return ax.plot(x, y, label=name, **kw)[0]


def apply_axes(ax, o: dict) -> None:
    """패널 하나에 편집 패널 값 적용: {x,y}{min,max,step,log,title}, y2title, legend. None·0·빈 문자열은 자동."""
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
            _hangul_math(getattr(ax, f"{a}axis").label)
    if o.get("y2title"):
        for t in _siblings(ax)[1:]:
            t.set_ylabel(o["y2title"])
            _hangul_math(t.yaxis.label)
    leg, rev = o.get("legend") or "자동", bool(o.get("legend_rev"))
    if leg == "숨김":
        _legend(ax, min_n=10**9)
    elif leg == "그래프 밖 오른쪽":
        _legend(ax, rev=rev, loc="upper left", bbox_to_anchor=(1.02, 1))
    elif leg != "자동":
        _legend(ax, rev=rev, loc=LEGEND_LOC[leg])
    elif rev:
        _legend(ax, min_n=2, rev=True)


def annotate(panels: list, notes: list[dict]) -> None:
    """주석(Origin Text·Arrow 도구): {text, x, y, tx?, ty?, panel?}. (x, y)는 데이터 좌표, tx·ty 를 주면 그 자리에 글을 두고
    (x, y)를 가리키는 화살표. 없는 패널 번호는 마지막 패널."""
    for n in notes:
        p = panels[min(max(int(n.get("panel") or 1), 1), len(panels)) - 1]
        arrow = n.get("tx") is not None and n.get("ty") is not None
        t = p.annotate(n["text"], xy=(n["x"], n["y"]), xytext=(n["tx"], n["ty"]) if arrow else None,
                       arrowprops={"arrowstyle": "->", "lw": 0.8} if arrow else None)
        _hangul_math(t)


def _hangul_math(label) -> None:
    """$수식$이 든 글은 matplotlib가 글꼴 목록 첫 글꼴 하나만 써서 한글이 □가 됨 — 그 글만 맑은 고딕(라틴 글자도 있음)으로."""
    s = label.get_text()
    if "$" in s and any("가" <= c <= "힣" or "ㄱ" <= c <= "ㆎ" for c in s):
        label.set_fontfamily(["Malgun Gothic"])


def _hide_empty(panels, axs) -> None:
    """시료가 하나도 없는 패널은 축을 숨김(빈 0~1 축 대신 빈 칸). 아무것도 안 그렸으면 그대로."""
    if axs:
        for p in panels:
            if not any(a in axs for a in _siblings(p)):
                p.set_axis_off()


def _labels(panels, xlabel, ylabel, stack: bool = False):
    """stack: X 제목은 맨 아래만, Y 제목은 그림 왼쪽에 하나, 범례는 칸마다(시료 하나씩)."""
    for p in panels:
        if not stack or p is panels[-1]:
            p.set_xlabel(xlabel)
        for a in _siblings(p):
            a.set_ylabel("" if stack else ylabel)
        _legend(p, min_n=1 if stack else 2)
    if stack:
        panels[0].figure.supylabel(ylabel, fontsize="medium")


def draw_vsm(fig: Figure, items: list[tuple[str, np.ndarray, np.ndarray, dict]], h_label: str, m_label: str,
             inset: bool = True, inset_half_width: float | None = None, layout: str = "한 그래프") -> list:
    """items: (표시명, H, M, 선 모양). inset이면 패널마다 원점 부근 확대(연자성 루프는 전체에서 Hc가 안 보임).
    돌려주는 값: 패널 축 목록(편집 값 적용용)."""
    panels, axs = _panels(fig, items, layout)
    lines = [_plot(ax, name, h, m, kw, k) for k, ((name, h, m, kw), ax) in enumerate(zip(items, axs))]
    _labels(panels, h_label, m_label, layout == STACK)
    hmax = max((float(np.abs(h).max()) for _, h, _, _ in items), default=1.0)
    w = inset_half_width or hmax * 0.02
    _hide_empty(panels, axs)
    for p in panels:
        if not p.axison:
            continue
        p.axhline(0, color="0.6", lw=0.5, zorder=0)
        p.axvline(0, color="0.6", lw=0.5, zorder=0)
        mine = [(it, ln) for it, ax, ln in zip(items, axs, lines) if ax is p]  # 오른쪽 Y축 시료는 눈금이 달라 인셋에서 뺌
        if not (inset and mine):
            continue
        ins = p.inset_axes([0.58, 0.08, 0.38, 0.38])
        for (_, h, m, _), ln in mine:
            il = ins.plot(h, m)[0]
            il.update_from(ln)  # 색·선 모양(흑백 사용자 파선 포함) 그대로
            il.set(lw=ln.get_linewidth() * 0.8, marker="")
        near = np.concatenate([m[np.abs(h) <= w] for (_, h, m, _), _ in mine])
        ins.set_xlim(-w, w)
        if near.size:
            mm = float(np.abs(near).max()) * 1.1 or 1.0
            ins.set_ylim(-mm, mm)
        ins.axhline(0, color="0.6", lw=0.4)
        ins.axvline(0, color="0.6", lw=0.4)
        ins.tick_params(labelsize="x-small")
        ins.locator_params(nbins=4)  # 패널이 작아지면 인셋 눈금 글자가 겹침
    return panels


OFFSET_MODES = ("일정 간격", "누적(겹치지 않게)")


def draw_xrd(fig: Figure, items: list[tuple[str, np.ndarray, np.ndarray, dict]], offset: float = 0.0,
             normalize: bool = True, layout: str = "한 그래프", offset_mode: str = "일정 간격") -> list:
    """items: (표시명, 2θ, counts, 선 모양). offset>0이면 같은 축 안에서 세로로 띄워 그린다(waterfall).
    일정 간격: i × offset(정규화 높이 기준). 누적: 앞 곡선 꼭대기 + offset 만큼 위(Origin Offset Cumulative)."""
    panels, axs = _panels(fig, items, layout)
    nth: dict = {}
    base: dict = {}
    for k, ((name, x, y, kw), ax) in enumerate(zip(items, axs)):
        top = float(y.max()) if y.size else 0.0
        scale = top if normalize and top > 0 else 1.0
        y = y / scale
        if kw.get("err") is not None:
            kw = {**kw, "err": kw["err"] / scale}
        i = nth[ax] = nth.get(ax, -1) + 1
        unit = 1 if normalize else top
        if offset_mode == OFFSET_MODES[1]:
            shift = base.get(ax, 0.0) - (float(y.min()) if i else 0.0)
            base[ax] = shift + float(y.max()) + offset * unit
        else:
            shift = i * offset * unit
        _plot(ax, name, x, y + shift, kw, k)
    _labels(panels, "2θ (°)", "Intensity (a.u.)" if normalize else "Intensity (counts)", layout == STACK)
    _hide_empty(panels, axs)
    if normalize:
        for a in fig.axes:
            a.set_yticklabels([])
    return panels


def save(fig: Figure, path: str | Path) -> Path:
    """PNG·TIF 600 dpi, SVG·PDF 벡터."""
    path = Path(path)
    fig.savefig(path, dpi=DPI.get(path.suffix.lower(), 600))
    return path


def png_bytes(fig: Figure, dpi: int = 300) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    return buf.getvalue()
