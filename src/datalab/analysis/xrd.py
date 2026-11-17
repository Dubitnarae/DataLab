"""XRD 해석 — xrdcheck 결과를 그대로 쓴다(판정·피크·Scherrer 재구현 금지, CLAUDE.md).

xrdcheck 내부 모듈을 부르는 곳은 이 파일 하나뿐이다. xrdcheck에 공개 API(api.py)가 생기면(M3) 여기만 바꾼다.
"""

from __future__ import annotations


def analyze(pattern):
    """xrdcheck AnalysisResult."""
    from xrdcheck.analysis.pipeline import analyze as _analyze

    return _analyze(pattern)


def summary(result) -> dict:
    """결과 표에 보여 줄 값(xrdcheck Excel 요약 행과 같은 열)."""
    from xrdcheck.report.excel import summary_row

    return {k: v for k, v in summary_row(result, []).items() if v not in (None, "")}
