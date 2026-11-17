"""피팅(Origin Fitting·Peak Analyzer 대응): 피크 함수 피팅, 랑주뱅·포화 접근 법칙 피팅.

피크 함수는 모두 넓이(A)·반치폭(w = FWHM)·중심(xc)으로 매개변수화한 교과서 식(Origin FitFunc 와 같은 뜻의 매개변수).
XRD 판정·피크 검출·Scherrer 는 xrdcheck 몫이고, 여기는 사용자가 구간과 함수를 고르는 수동 피팅만 한다.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import curve_fit
from scipy.special import gammaln

LN2 = np.log(2)


def gauss(x, xc, w, a):
    return a * np.sqrt(4 * LN2 / np.pi) / w * np.exp(-4 * LN2 * ((x - xc) / w) ** 2)


def lorentz(x, xc, w, a):
    return 2 * a / np.pi * w / (4 * (x - xc) ** 2 + w ** 2)


def pvoigt(x, xc, w, a, mu):
    """mu = 로렌츠 비율(0 가우스 ~ 1 로렌츠)."""
    return mu * lorentz(x, xc, w, a) + (1 - mu) * gauss(x, xc, w, a)


def pearson7(x, xc, w, a, m):
    """m → 1 로렌츠, m → ∞ 가우스. 넓이 정규화: ∫ = a."""
    k = 2 ** (1 / m) - 1
    norm = 2 * np.sqrt(k) / (np.sqrt(np.pi) * w) * np.exp(gammaln(m) - gammaln(m - 0.5))
    return a * norm * (1 + 4 * k * ((x - xc) / w) ** 2) ** (-m)


# 이름: (함수, 모양 매개변수 이름·초기값·범위 또는 None)
PEAKS = {"Gauss": (gauss, None), "Lorentz": (lorentz, None),
         "pseudo-Voigt": (pvoigt, ("mu", 0.5, (0.0, 1.0))), "Pearson VII": (pearson7, ("m", 2.0, (0.51, 50.0)))}
BASELINES = {"없음": 0, "상수": 1, "직선": 2}


def guess_centers(x, y, n: int) -> list[float]:
    """구간 안 두드러진 피크 n개(돌출도 순)의 위치, X 순서로."""
    from scipy.signal import find_peaks

    x, y = np.asarray(x, float), np.asarray(y, float)
    idx, prop = find_peaks(y, prominence=np.ptp(y) * 0.03 if np.ptp(y) > 0 else None)
    if idx.size == 0:
        return [float(x[np.argmax(y)])]
    top = idx[np.argsort(prop["prominences"])[::-1][:n]]
    return sorted(float(x[i]) for i in top)


def fit_peaks(x, y, kind: str = "pseudo-Voigt", centers: list[float] | None = None, n: int = 1,
              baseline: str = "상수") -> dict:
    """피크 여러 개 + 바탕선 동시 피팅. centers 가 없으면 guess_centers(n).

    돌려줌: peaks [{xc, w(FWHM), area, height, shape?, *_err}], base [계수], r2, curve(x), parts(x)·base_curve(x) 함수.
    """
    f, shape = PEAKS[kind]
    x, y = np.asarray(x, float), np.asarray(y, float)
    o = np.argsort(x)
    x, y = x[o], y[o]
    if x.size < 5:
        raise ValueError("피팅할 점이 5개 미만입니다.")
    centers = list(centers or guess_centers(x, y, n))
    nb = BASELINES[baseline]
    span = float(x[-1] - x[0])
    step = float(np.median(np.diff(x))) or span / x.size
    y0 = float(np.min(y)) if nb else 0.0
    p0, lo, hi = [], [], []
    if nb >= 1:
        p0 += [y0]
        lo += [-np.inf]
        hi += [np.inf]
    if nb == 2:
        p0 += [0.0]
        lo += [-np.inf]
        hi += [np.inf]
    npar = 3 + (shape is not None)
    for c in centers:
        h = float(np.interp(c, x, y)) - y0
        w = max(span / (6 * len(centers)), 3 * step)
        p0 += [c, w, max(h, 1e-12) * w * 1.064]
        lo += [x[0], step * 0.5, 0.0]
        hi += [x[-1], span, np.inf]
        if shape:
            p0.append(shape[1])
            lo.append(shape[2][0])
            hi.append(shape[2][1])

    def base(xx, *p):
        return (p[0] if nb >= 1 else 0.0) + (p[1] * (xx - x[0]) if nb == 2 else 0.0)

    def model(xx, *p):
        out = base(xx, *p)
        for k in range(len(centers)):
            out = out + f(xx, *p[nb + k * npar: nb + (k + 1) * npar])
        return out

    p, cov = curve_fit(model, x, y, p0=np.clip(p0, lo, hi), bounds=(lo, hi), maxfev=20000)
    err = np.sqrt(np.clip(np.diag(cov), 0, None)) if np.all(np.isfinite(cov)) else np.full(p.size, np.nan)
    resid = y - model(x, *p)
    ss = float(np.sum((y - y.mean()) ** 2))
    peaks = []
    for k in range(len(centers)):
        q, e = p[nb + k * npar: nb + (k + 1) * npar], err[nb + k * npar: nb + (k + 1) * npar]
        d = {"xc": q[0], "xc_err": e[0], "w": q[1], "w_err": e[1], "area": q[2], "area_err": e[2],
             "height": float(f(q[0], *q))}
        if shape:
            d[shape[0]], d[shape[0] + "_err"] = q[3], e[3]
        peaks.append({k2: float(v) for k2, v in d.items()})
    return {"kind": kind, "peaks": peaks, "base": [float(v) for v in p[:nb]], "r2": 1 - float(resid @ resid) / ss if ss else None,
            "curve": lambda xx: model(np.asarray(xx, float), *p),
            "base_curve": lambda xx: base(np.asarray(xx, float), *p) + np.zeros(np.size(xx)),
            "parts": [lambda xx, q=p[nb + k * npar: nb + (k + 1) * npar]: f(np.asarray(xx, float), *q)
                      for k in range(len(centers))]}


def langevin(z):
    """L(z) = coth z − 1/z, 0 근처는 z/3(0으로 나누기 피함)."""
    z = np.asarray(z, float)
    small = np.abs(z) < 1e-4
    zs = np.where(small, 1.0, z)
    return np.where(small, z / 3, 1 / np.tanh(zs) - 1 / zs)


def fit_langevin(h, m) -> dict:
    """M = Ms·L((H − H0)/a) + χ·H (Origin LANGEVIN 에 고자장 기울기 χ 를 더함). 이력은 무시(두 가지 평균에 맞춰짐).
    a = kT/(μ0·m) 의 자장 단위 값. 돌려줌: Ms, a, H0, chi, r2, *_err, curve."""
    h, m = np.asarray(h, float), np.asarray(m, float)
    ms0 = float(np.ptp(m)) / 2 or 1.0
    a0 = float(np.abs(h).max()) / 20 or 1.0

    def model(x, ms, a, h0, chi):
        return ms * langevin((x - h0) / a) + chi * x

    p, cov = curve_fit(model, h, m, p0=[ms0, a0, 0.0, 0.0],
                       bounds=([0, 1e-12, -np.inf, -np.inf], [np.inf, np.inf, np.inf, np.inf]), maxfev=20000)
    return _pack(("Ms", "a", "H0", "chi"), p, cov, h, m, lambda x: model(np.asarray(x, float), *p))


SAT_TERMS = ("a", "b", "chi")


def fit_saturation(h, m, frac: float = 0.5, terms=("b", "chi")) -> dict:
    """포화 접근 법칙: |H| ≥ frac·H최대 에서 M·sign(H) = Ms(1 − a/|H| − b/H²) + χ|H|. 양쪽 가지를 합쳐 맞춘다.
    terms: 넣을 항(a·b·chi). 고자장 구간이 좁으면 항끼리 겹쳐(공선성) 값이 흔들리므로 기본은 b·χ 만.
    돌려줌: Ms, a, b, chi(안 넣은 항은 0), r2, *_err, n, curve(H) — 맞춘 구간 밖은 NaN."""
    h, m = np.asarray(h, float), np.asarray(m, float)
    hmax = float(np.abs(h).max())
    sel = np.abs(h) >= frac * hmax
    if sel.sum() < 5:
        raise ValueError("맞출 고자장 점이 5개 미만입니다. 비율을 낮추세요.")
    x, y = np.abs(h[sel]), m[sel] * np.sign(h[sel])
    use = [t for t in SAT_TERMS if t in terms]

    def full(xx, ms, a=0.0, b=0.0, chi=0.0):
        return ms * (1 - a / xx - b / xx ** 2) + chi * xx

    def model(xx, ms, *q):
        return full(xx, ms, **dict(zip(use, q)))

    p, cov = curve_fit(model, x, y, p0=[float(np.median(y))] + [0.0] * len(use), maxfev=20000)

    def curve(xx):
        xx = np.asarray(xx, float)
        ok = np.abs(xx) >= frac * hmax
        return np.where(ok, np.sign(xx) * model(np.where(ok, np.abs(xx), 1.0), *p), np.nan)

    r = _pack(("Ms", *use), p, cov, x, y, lambda xx: model(np.asarray(xx, float), *p))
    for t in SAT_TERMS:
        r.setdefault(t, 0.0)
        r.setdefault(t + "_err", None)
    r.update(curve=curve, n=int(sel.sum()), terms=use)
    return r


def _pack(names, p, cov, x, y, curve) -> dict:
    err = np.sqrt(np.clip(np.diag(cov), 0, None)) if np.all(np.isfinite(cov)) else np.full(len(p), np.nan)
    resid = y - curve(x)
    ss = float(np.sum((y - y.mean()) ** 2))
    out = {k: float(v) for k, v in zip(names, p)}
    out.update({k + "_err": float(e) for k, e in zip(names, err)})
    out.update(r2=1 - float(resid @ resid) / ss if ss else None, curve=curve)
    return out
