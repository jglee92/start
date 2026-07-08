# -*- coding: utf-8 -*-
"""
PEAD(실적발표 후 드리프트) 리서치.

DART는 분기 손익을 '누적'으로만 제공한다(1Q=단독, 반기=1~2Q누적, 3Q보고서=1~3Q누적,
사업보고서=연간). 표준 분기(단독) 실적으로 바꾸려면 뺄셈이 필요하다:
  Q1 = 1Q 누적(그대로)
  Q2 = 반기누적 - Q1
  Q3 = 3Q누적 - 반기누적
  Q4 = 연간 - 3Q누적

SUE(표준화 예상외 실적, Bernard-Thomas 방식. 애널리스트 컨센서스 없이 계산 가능):
  surprise_t = E_t - E_{t-4}  (전년 동기 대비 변화)
  SUE_t = surprise_t / stdev(surprise_{t-1..t-8})  (최근 8개 서프라이즈의 표준편차로 표준화)
"""
from __future__ import annotations
import statistics

REPRT = {1: "11013", 2: "11012", 3: "11014", 4: "11011"}  # quarter -> DART reprt_code(누적)


def standalone_from_cumulative(q1, half, q3, annual):
    """4개 누적 dict(없으면 None) -> {1:{...},2:{...},3:{...},4:{...}} 표준분기(단독).
    revenue/op_profit/net_income은 뺄셈으로 단독분기화. debt_ratio(재무상태표 항목)는
    원래 그 분기 시점 스냅샷이라 빼기 불필요 — 해당 분기 보고서 값을 그대로 쓰고,
    op_margin은 단독분기 revenue/op_profit으로 재계산(누적 op_margin을 그대로 쓰면 틀림)."""
    def sub(a, b, keys=("revenue", "op_profit", "net_income")):
        if a is None or b is None:
            return None
        out = {}
        for k in keys:
            av, bv = a.get(k), b.get(k)
            out[k] = (av - bv) if (av is not None and bv is not None) else None
        return out

    out = {1: q1, 2: sub(half, q1), 3: sub(q3, half), 4: sub(annual, q3)}
    for q, cum in ((1, q1), (2, half), (3, q3), (4, annual)):
        row = out.get(q)
        if row is None:
            continue
        row["debt_ratio"] = cum.get("debt_ratio") if cum else None
        rev, op = row.get("revenue"), row.get("op_profit")
        row["op_margin"] = (op / rev * 100) if (op is not None and rev) else None
    return out


def compute_sue_series(series):
    """series: get_quarterly_series() 결과(연·분기 오름차순, 연속 보장X).
    각 원소에 'sue'(표준화 예상외 실적, net_income 기준) 필드를 추가해 반환.
    최소 전년동기 1개 + 최근 8개 서프라이즈 필요 -> 앞쪽 다수는 sue=None."""
    idx = {(r["year"], r["quarter"]): i for i, r in enumerate(series)}
    surprises = [None] * len(series)
    for i, r in enumerate(series):
        prev = idx.get((r["year"] - 1, r["quarter"]))
        if prev is None or r["net_income"] is None or series[prev]["net_income"] is None:
            continue
        surprises[i] = r["net_income"] - series[prev]["net_income"]
    out = []
    for i, r in enumerate(series):
        hist = [s for s in surprises[max(0, i - 8):i] if s is not None]
        sue = None
        if surprises[i] is not None and len(hist) >= 4:
            sd = statistics.pstdev(hist)
            if sd > 0:
                sue = surprises[i] / sd
        out.append({**r, "sue": sue})
    return out
