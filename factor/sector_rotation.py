# -*- coding: utf-8 -*-
"""
섹터 로테이션 분석 (카테고리 백테스트).

각 연도(5월→이듬해 5월) 섹터별 동일가중 수익률(배당·상폐 포함)을 계산해
'어느 섹터가 언제 강했나'를 보여준다. 시점정합 유니버스(시총 필터) 기준.
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import factor_config as cfg
import db
from factor.universe import build_master, eligible_at
from factor.data import price_asof
from factor.backtest import rebal_date, ew_return
from factor.sectors import classify


def _year_universe_by_sector(conn, master, year):
    elig = eligible_at(master, rebal_date(year), cfg)
    buckets = {}
    for r in elig.itertuples(index=False):
        if r.shares is None:
            continue
        p = price_asof(conn, r.code, rebal_date(year))
        if not p or r.shares * p[0] < cfg.MIN_MARKET_CAP:
            continue
        sec = classify(getattr(r, "industry", None), r.code)
        buckets.setdefault(sec, []).append(r.code)
    return buckets


def compute_rotation(conn, master=None):
    if master is None:
        master = build_master()
    max_date = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
    max_year = int(max_date[:4])
    years = list(range(cfg.BT_START_YEAR, max_year + 1))
    # 섹터 -> {year: ret}
    grid = {}
    counts = {}
    partial_years = []
    for y in years:
        buy = rebal_date(y)
        if buy > max_date:        # 아직 리밸일 도래 전
            continue
        full_sell = rebal_date(y + 1)
        partial = full_sell > max_date
        sell = max_date if partial else full_sell
        if partial and str(y) not in partial_years:
            partial_years.append(str(y))
        div_year = None if partial else y   # 진행중이면 배당 미가산
        buckets = _year_universe_by_sector(conn, master, y)
        for sec, codes in buckets.items():
            ret, n = ew_return(conn, codes, buy, sell, div_year)  # 배당 포함(완결년)
            if ret is not None:
                grid.setdefault(sec, {})[y] = round(ret * 100, 1)
                counts.setdefault(sec, {})[y] = n
    years = [y for y in years if any(y in grid[s] for s in grid)]
    # 정렬: 평균수익 높은 섹터 순
    full_years = [y for y in years if str(y) not in partial_years]
    rows = []
    for sec, yr in grid.items():
        vals = [yr[y] for y in full_years if y in yr]   # 평균은 완결년만
        rows.append({
            "sector": sec,
            "returns": {str(y): yr.get(y) for y in years},
            "avg": round(sum(vals) / len(vals), 1) if vals else None,
            "count_last": counts.get(sec, {}).get(years[-1], 0),
        })
    rows.sort(key=lambda r: (r["avg"] is not None, r["avg"]), reverse=True)
    # 각 연도 최강 섹터 표시용
    best = {}
    for y in years:
        cands = [(r["sector"], r["returns"][str(y)]) for r in rows
                 if r["returns"][str(y)] is not None]
        if cands:
            best[str(y)] = max(cands, key=lambda x: x[1])[0]
    return {"years": [str(y) for y in years], "rows": rows, "best": best,
            "partial_years": partial_years}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    conn = db.connect()
    rot = compute_rotation(conn)
    hdr = "섹터".ljust(16) + "".join(y[2:] + "  " for y in rot["years"]) + "  평균"
    print(hdr)
    for r in rot["rows"]:
        line = r["sector"].ljust(16)
        for y in rot["years"]:
            v = r["returns"][y]
            line += (f"{v:>5.0f} " if v is not None else "    . ")
        line += f"  {r['avg']}"
        print(line)
    print("\n연도별 최강섹터:", rot["best"])
    conn.close()
