"""VSM M-H 루프 해석: Hc·Mr·Ms·각형비. GUI와 분리된 순수 함수.

장비(Lake Shore 8600) 계산식을 그대로 따른다(실측 csv 3,082개로 확인 — AI 오피스 vsm.ts):
- Hc = M이 0을 지나는 자장들의 절댓값 평균, Mr = H가 0을 지날 때 M들의 절댓값 평균.
- 루프가 한쪽으로 치우치면(두 교차점이 같은 부호) 이 Hc는 실제 반폭보다 크다 → Hc_half(반폭)·H_bias를 함께 낸다.
- Ms = (M 최댓값 − 최솟값)/2. 장비 값과 0.2 % 안팎.
"""

from __future__ import annotations

import numpy as np

ANALYSIS_VERSION = "vsm-1"
OE_TO_A_PER_M = 1000 / (4 * np.pi)  # 1 Oe = 79.577 A/m


def crossings(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """y가 0을 지나는 지점의 x(선형 보간). 0에서 시작하는 구간·평평한 구간은 뺀다."""
    a, b = y[:-1], y[1:]
    ok = (a != b) & (a * b <= 0) & (a != 0)
    x0, x1 = x[:-1][ok], x[1:][ok]
    return x0 + (x1 - x0) * (-a[ok]) / (b[ok] - a[ok])


def high_field_slope(h: np.ndarray, m: np.ndarray, frac: float = 0.7) -> float | None:
    """|H| ≥ frac·H최대 구간의 배경 기울기 χ(M/H 단위, Origin subtract_line).

    M = χH + a·sign(H) + b로 맞춘다 — 양쪽 포화값 ±Ms를 a가 받아서 기울기가 Ms/H 쪽으로 쏠리지 않는다.
    점이 4개 미만이면 None.
    """
    h, m = np.asarray(h, float), np.asarray(m, float)
    sel = np.abs(h) >= frac * np.abs(h).max()
    if sel.sum() < 4 or np.ptp(h[sel]) == 0:
        return None
    a = np.c_[h[sel], np.sign(h[sel]), np.ones(sel.sum())]
    return float(np.linalg.lstsq(a, m[sel], rcond=None)[0][0])


def dmdh(h: np.ndarray, m: np.ndarray) -> np.ndarray:
    """측정 순서대로의 dM/dH(스위칭 자장 분포). 루프 끝 되돌이점처럼 H가 거의 안 변하는 곳은 NaN(끊어 그림)."""
    # shortcut: 평활화 없음 — 잡음 많은 파일에서 뾰족하면 이동평균 옵션 추가
    dh, dm = np.gradient(np.asarray(h, float)), np.gradient(np.asarray(m, float))
    ok = np.abs(dh) > 0.1 * np.median(np.abs(dh))
    return np.where(ok, dm / np.where(ok, dh, 1.0), np.nan)


def analyze_loop(h: np.ndarray, m: np.ndarray, field_offset: float = 0.0, slope: float = 0.0) -> dict:
    """field_offset: 전자석 잔류자장 보정값(H 단위). H − offset으로 계산한다.
    slope: 뺄 배경 기울기 χ(high_field_slope). M − χ·(H − offset)으로 계산한다.

    돌려주는 값(H·M 원본 단위): Hc, Hc_half, H_bias, Mr, Ms, SQ, H_max, shifted, n_points, field_offset.
    계산할 수 없는 값은 None.
    """
    h = np.asarray(h, float) - field_offset
    m = np.asarray(m, float) - slope * h
    hx, mx = crossings(h, m), crossings(m, h)
    ms = (m.max() - m.min()) / 2
    mr = float(np.abs(mx).mean()) if mx.size else None
    # 교차점이 정확히 2개일 때만 반폭을 낸다(0 근처 잡음으로 여러 번 지나면 믿을 수 없음)
    two = hx.size == 2
    return {
        "Hc": float(np.abs(hx).mean()) if hx.size else None,
        "Hc_half": float(abs(hx[0] - hx[1]) / 2) if two else None,
        "H_bias": float(hx.mean()) if two else None,
        "Mr": mr,
        "Ms": float(ms),
        "SQ": mr / ms if mr is not None and ms > 0 else None,
        "H_max": float(np.abs(h).max()),
        "shifted": bool(two and hx[0] * hx[1] > 0),
        "n_points": int(h.size),
        "field_offset": float(field_offset),
    }


def compare_device(result: dict, device: dict) -> list[str]:
    """장비 계산값과 다르면 설명 목록. 허용: Hc·Mr 0.1 %, Ms 2 %(장비 Ms 식 미확인)."""
    out = []
    for key, rel in (("Hc", 1e-3), ("Mr", 1e-3), ("Ms", 0.02)):
        d, c = device.get(key), result.get(key)
        if d is None:
            continue
        if c is None:
            out.append(f"{key} 계산 불가(장비 {d:.4g})")
        elif abs(d - c) > max(1e-9, abs(d) * rel):
            out.append(f"{key} 장비 {d:.4g} ≠ 계산 {c:.4g}")
    return out
