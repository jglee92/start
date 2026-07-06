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
    g, g2 = r.get("rev_growth"), r.get("rev_growth_prev")
    if g is None:
        return "전년 대비 비교 가능한 재무 데이터가 부족합니다."
    dir_ = "증가" if g >= 0 else "감소"
    txt = f"전년 대비 매출이 {abs(g):.1f}% {dir_}했습니다.{_cmp(g, sec.get('growth'), '%')}"
    if g2 is not None:
        if g > 0 and g2 > 0:
            trend = "가속" if g >= g2 else "둔화(그러나 2년 연속 성장)"
            txt += f" 그 전년에도 {g2:+.1f}%로, 성장이 {trend} 흐름입니다."
        elif g > 0 and g2 <= 0:
            txt += f" 직전 2년째 역성장(전년 {g2:+.1f}%)에서 최근 성장으로 전환됐습니다."
        elif g <= 0 and g2 > 0:
            txt += f" 그 전년({g2:+.1f}%)엔 성장했으나 최근 둔화됐습니다."
        else:
            txt += f" 2년 연속 역성장({g2:+.1f}% → {g:+.1f}%)입니다."
    return txt


def anomaly_flags(r, pf):
    """재무 이상신호(참고용, 회계부정 진단 아님) — 이미 확보한 다년치 데이터로만 판단."""
    flags = []
    ni, op, dr = r.get("net_income"), r.get("op_profit"), r.get("debt_ratio")
    g, g2 = r.get("rev_growth"), r.get("rev_growth_prev")

    if pf and pf.get("net_income") is not None and ni is not None:
        if pf["net_income"] > 0 and ni <= 0:
            flags.append({"emoji": "🔴", "label": "적자 전환",
                         "text": "전년 흑자에서 올해 적자로 전환됐습니다."})
    if op is not None and ni is not None and op < 0 and ni > 0:
        flags.append({"emoji": "🟡", "label": "영업외 손익 의존",
                     "text": "영업이익은 적자이나 순이익은 흑자입니다. "
                             "본업 외 손익(자산매각·평가이익 등)에 기댄 결과일 수 있습니다."})
    if pf and pf.get("debt_ratio") is not None and dr is not None and (dr - pf["debt_ratio"]) >= 50:
        dr_r, pf_r = round(dr), round(pf["debt_ratio"])   # 표시값 기준으로 차이도 계산(반올림 불일치 방지)
        flags.append({"emoji": "🟡", "label": "부채비율 급증",
                     "text": f"부채비율이 전년 {pf_r:.0f}%에서 {dr_r:.0f}%로 "
                             f"{dr_r-pf_r:.0f}%p 급증했습니다."})
    if g is not None and g2 is not None and g < 0 and g2 < 0:
        flags.append({"emoji": "🟡", "label": "매출 2년 연속 감소",
                     "text": "최근 2개 회계연도 모두 매출이 전년보다 감소했습니다."})
    return flags


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
