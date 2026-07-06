# -*- coding: utf-8 -*-
"""
규칙 기반 '해석' 엔진. LLM 호출 없이, 백분위·업종평균 비교로 별점(1~5)과
평이한 설명 문장을 생성한다. "숫자보다 해석이 중요하다"는 원칙을 구현.

4개 심사 차원(모두 유니버스 내 백분위 0~1 기준, 종합 팩터점수와는 별개):
  밸류에이션(저평가일수록↑) · 수익성(ROE/영업이익률) · 안정성(부채낮을수록↑) · 성장성(매출증가율)
"""
from __future__ import annotations

LABELS = [(0.8, "매우 우수"), (0.6, "우수"), (0.4, "보통"), (0.2, "미흡"), (0.0, "부족")]


def _stars(pctl):
    if pctl is None:
        return None
    return max(1, min(5, round(pctl * 5) or 1))


def _label(pctl):
    if pctl is None:
        return "데이터 없음"
    for th, lb in LABELS:
        if pctl >= th:
            return lb
    return "부족"


def sector_averages(rows):
    """섹터별 평균 ROE/PER/부채비율/매출성장률 (해석 문장의 '업종평균 대비' 근거)."""
    buckets = {}
    for r in rows:
        b = buckets.setdefault(r.get("sector") or "기타",
                               {"roe": [], "per": [], "debt": [], "growth": []})
        if r.get("roe") is not None:
            b["roe"].append(r["roe"])
        if r.get("per") is not None and r["per"] > 0:
            b["per"].append(r["per"])
        if r.get("debt_ratio") is not None:
            b["debt"].append(r["debt_ratio"])
        if r.get("rev_growth") is not None:
            b["growth"].append(r["rev_growth"])
    avg = {}
    for sec, b in buckets.items():
        avg[sec] = {k: (round(sum(v) / len(v), 1) if v else None)
                   for k, v in b.items()}
    return avg


def dimension_grades(r, sector_avg):
    """4차원 별점+등급+해석문장. r은 breakdown(백분위) 포함된 랭킹 row."""
    bd = r.get("breakdown", {})
    sec = sector_avg.get(r.get("sector") or "기타", {})

    value_pctl = _avg(bd.get("_ey"), bd.get("_by"))
    profit_pctl = _avg(bd.get("_roe"), bd.get("_opm"))
    safety_pctl = bd.get("_lowdebt")
    growth_pctl = bd.get("_growth")

    dims = {
        "value": {"stars": _stars(value_pctl), "label": _label(value_pctl),
                  "text": _value_text(r, sec)},
        "profit": {"stars": _stars(profit_pctl), "label": _label(profit_pctl),
                   "text": _profit_text(r, sec)},
        "safety": {"stars": _stars(safety_pctl), "label": _label(safety_pctl),
                   "text": _safety_text(r, sec)},
        "growth": {"stars": _stars(growth_pctl), "label": _label(growth_pctl),
                   "text": _growth_text(r, sec)},
    }
    dims["overall_text"] = _overall_text(r, dims)
    return dims


def _avg(*vals):
    vs = [v for v in vals if v is not None]
    return sum(vs) / len(vs) if vs else None


def _cmp(v, avg, unit="", higher_better=True):
    if v is None or avg is None:
        return ""
    diff = "높습니다" if (v > avg) == higher_better else "낮습니다"
    return f" 업종평균({avg:.1f}{unit})보다 {diff}."


def _value_text(r, sec):
    per, pbr = r.get("per"), r.get("pbr")
    if per is None:
        return "밸류에이션 데이터가 부족합니다."
    base = f"PER {per:.1f}배"
    if pbr is not None:
        base += f", PBR {pbr:.2f}배"
    return base + f"입니다.{_cmp(per, sec.get('per'), '배', higher_better=False)}"


def _profit_text(r, sec):
    roe = r.get("roe")
    if roe is None:
        return "수익성 데이터가 부족합니다."
    return f"ROE {roe:.1f}%입니다.{_cmp(roe, sec.get('roe'), '%')}"


def _safety_text(r, sec):
    dr = r.get("debt_ratio")
    if dr is None:
        return "부채 데이터가 부족합니다."
    base = f"부채비율 {dr:.0f}%입니다.{_cmp(dr, sec.get('debt'), '%', higher_better=False)}"
    if dr < 50:
        base += " 100% 미만은 통상 안전한 수준으로 봅니다."
    elif dr > 200:
        base += " 200%를 넘으면 부채 부담이 큰 편입니다."
    return base


def _growth_text(r, sec):
    g = r.get("rev_growth")
    if g is None:
        return "전년 대비 비교 가능한 재무 데이터가 부족합니다."
    dir_ = "증가" if g >= 0 else "감소"
    return f"전년 대비 매출이 {abs(g):.1f}% {dir_}했습니다.{_cmp(g, sec.get('growth'), '%')}"


def _overall_text(r, dims):
    best = max(dims.items(), key=lambda kv: kv[1]["stars"] or 0,
              default=(None, None))
    worst = min(((k, v) for k, v in dims.items() if v["stars"]),
               key=lambda kv: kv[1]["stars"], default=(None, None))
    name = {"value": "밸류에이션", "profit": "수익성", "safety": "안정성",
            "growth": "성장성"}
    parts = []
    if best[0]:
        parts.append(f"{name[best[0]]}이 상대적으로 강점")
    if worst[0] and worst[0] != best[0]:
        parts.append(f"{name[worst[0]]}은 상대적으로 약점")
    return " · ".join(parts) + " (같은 유니버스 내 상대 비교)." if parts else ""
