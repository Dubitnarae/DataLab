"""데이터 처리(Origin Data Manipulation·Mathematics·Signal Processing 대응). GUI와 분리된 순수 함수.

원본 배열은 바꾸지 않고, 처리 설정(dict)만 시료에 붙여 그릴 때마다 새로 계산한다.
처리 순서: 해석 구간 → 뺀 점 → 기준 곡선 빼기 → 평활화.
"""

from __future__ import annotations

import numpy as np

from datalab.analysis.vsm import smooth as moving_average


def sweep(x: np.ndarray) -> np.ndarray:
    """측정 방향: +1 올라감, −1 내려감, 0 멈춤(루프 끝 되돌이점)."""
    return np.sign(np.gradient(np.asarray(x, float))) if len(x) > 1 else np.zeros(len(x))


def interp_ref(x: np.ndarray, xr: np.ndarray, yr: np.ndarray) -> np.ndarray:
    """기준 곡선 값을 x 위치에서. 루프(VSM)는 같은 방향 가지끼리 보간(내려가는 점은 기준의 내려가는 가지).
    기준 범위 밖은 끝값으로 둔다(공통 구간만 빼기는 apply에서 거름)."""
    x, xr, yr = (np.asarray(a, float) for a in (x, xr, yr))
    out = np.full(x.size, np.nan)
    sx, sr = sweep(x), sweep(xr)
    for s in (-1, 1):
        sel = sr == s
        if sel.sum() >= 2:
            o = np.argsort(xr[sel])
            m = sx == s
            out[m] = np.interp(x[m], xr[sel][o], yr[sel][o])
    left = np.isnan(out)  # 멈춘 점, 한쪽 가지만 있는 기준
    if left.any():
        o = np.argsort(xr)
        out[left] = np.interp(x[left], xr[o], yr[o])
    return out


def savgol(y: np.ndarray, n: int, order: int) -> np.ndarray:
    """Savitzky-Golay. 창은 홀수로 올리고 차수는 창보다 작게."""
    from scipy.signal import savgol_filter

    y = np.asarray(y, float)
    n = min(int(n) | 1, y.size if y.size % 2 else y.size - 1)
    if n < 3:
        return y
    return savgol_filter(y, n, min(int(order), n - 1))


def apply(x, y, err=None, p: dict | None = None, ref: tuple | None = None):
    """p: xmin·xmax(None=끝까지), drop(뺄 점 번호), common_only, smooth("aav"|"sg"), smooth_n, smooth_order.
    ref: 기준 곡선 (x, y). 돌려줌: (x, y, err) — 남은 점만."""
    p = p or {}
    x, y = np.asarray(x, float), np.asarray(y, float)
    keep = np.ones(x.size, bool)
    if p.get("xmin") is not None:
        keep &= x >= p["xmin"]
    if p.get("xmax") is not None:
        keep &= x <= p["xmax"]
    drop = [i for i in p.get("drop", ()) if 0 <= i < x.size]
    keep[drop] = False
    if ref is not None:
        rx = np.asarray(ref[0], float)
        y = y - interp_ref(x, rx, ref[1])
        if p.get("common_only"):
            keep &= (x >= rx.min()) & (x <= rx.max())
    x, y = x[keep], y[keep]
    err = np.asarray(err, float)[keep] if err is not None else None
    n = int(p.get("smooth_n") or 0)
    if n >= 2 and p.get("smooth") == "sg":
        y = savgol(y, n, p.get("smooth_order") or 2)
    elif n >= 2 and p.get("smooth"):
        y = moving_average(y, n)
    return x, y, err


def describe(p: dict) -> str:
    """결과 표에 붙일 처리 요약(어떤 값이 원본과 다른지 알 수 있게)."""
    out = []
    if p.get("xmin") is not None or p.get("xmax") is not None:
        lo = "" if p.get("xmin") is None else f"{p['xmin']:g}"
        hi = "" if p.get("xmax") is None else f"{p['xmax']:g}"
        out.append(f"구간 {lo}~{hi}")
    if p.get("drop"):
        out.append(f"뺀 점 {len(p['drop'])}개")
    if p.get("ref") is not None:
        out.append("기준 빼기" + ("(공통 구간)" if p.get("common_only") else ""))
    if int(p.get("smooth_n") or 0) >= 2 and p.get("smooth"):
        out.append(("S-G " if p["smooth"] == "sg" else "이동평균 ") + f"{int(p['smooth_n'])}점")
    return ", ".join(out) or "없음"


def find_spikes(y, n: int = 7, z: float = 6.0) -> list[int]:
    """튀는 점 후보: n점 중앙값에서 벗어난 정도가 잡음(MAD)의 z배 넘는 점 번호. 사용자가 보고 고른다."""
    from scipy.signal import medfilt

    y = np.asarray(y, float)
    if y.size < 5:
        return []
    r = y - medfilt(y, min(int(n) | 1, y.size if y.size % 2 else y.size - 1))
    # 매끈한(단조) 구간은 중앙값이 제 값이라 MAD가 0이 됨 → 데이터 폭의 0.1 %를 바닥으로
    scale = max(1.4826 * float(np.median(np.abs(r - np.median(r)))), 1e-3 * float(np.ptp(y)))
    if scale == 0:
        return []
    return [int(i) for i in np.flatnonzero(np.abs(r) > z * scale)]


def integrate(x, y, lo=None, hi=None, absolute: bool = False) -> dict:
    """측정 순서대로 사다리꼴 적분(Origin integ1). 루프면 둘러싼 면적(이력 손실)이 나온다.
    돌려줌: area, y_max, x_at_max, fwhm(반값 양쪽 교차점 사이, 못 찾으면 None), n."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    sel = np.ones(x.size, bool)
    if lo is not None:
        sel &= x >= lo
    if hi is not None:
        sel &= x <= hi
    x, y = x[sel], y[sel]
    if x.size < 2:
        return {"area": None, "y_max": None, "x_at_max": None, "fwhm": None, "n": int(x.size)}
    area = float(np.trapezoid(np.abs(y) if absolute else y, x))
    i = int(np.argmax(y))
    half = y[i] / 2
    fwhm = None
    left = np.flatnonzero(y[:i] < half)
    right = np.flatnonzero(y[i:] < half)
    if left.size and right.size:
        a, b = left[-1], i + right[0]
        xl = np.interp(half, [y[a], y[a + 1]], [x[a], x[a + 1]])
        xr = np.interp(half, [y[b], y[b - 1]], [x[b], x[b - 1]])
        fwhm = float(abs(xr - xl))
    return {"area": area, "y_max": float(y[i]), "x_at_max": float(x[i]), "fwhm": fwhm, "n": int(x.size)}


def interp_at(x, y, xs, method: str = "linear") -> dict[str, np.ndarray]:
    """주어진 X에서 Y(Origin interp1). 한 방향 데이터는 {"Y"}, 루프는 가지별 {"내려가는 가지", "올라가는 가지"}.
    method: linear | spline(3차). 범위 밖은 NaN."""
    from scipy.interpolate import CubicSpline

    x, y, xs = np.asarray(x, float), np.asarray(y, float), np.atleast_1d(np.asarray(xs, float))
    s = sweep(x)
    groups = {"Y": np.ones(x.size, bool)} if (s >= 0).all() or (s <= 0).all() else \
        {"내려가는 가지": s < 0, "올라가는 가지": s > 0}
    out = {}
    for name, sel in groups.items():
        gx, gy = x[sel], y[sel]
        gx, idx = np.unique(gx, return_index=True)
        gy = gy[idx]
        if gx.size < 2:
            out[name] = np.full(xs.size, np.nan)
            continue
        v = CubicSpline(gx, gy)(xs) if method == "spline" and gx.size >= 4 else np.interp(xs, gx, gy)
        out[name] = np.where((xs >= gx[0]) & (xs <= gx[-1]), v, np.nan)
    return out
