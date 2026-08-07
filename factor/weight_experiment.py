# -*- coding: utf-8 -*-
"""건강점수 가중치 실험 하니스 (데이터 1회 로드 → 여러 가중치 조합 재채점).

원리: 주식별 팩터 원값(ey/by/sy/roe/opm/lowdebt[/growth])과 주식별 실현수익률은
가중치와 무관하다. 따라서 연도별 유니버스·팩터원값·수익률을 '한 번' 계산해두고,
가중치 조합만 바꿔 pct_rank 가중합 → TOP_N 선택 → 수익 집계를 재실행한다.
factor/backtest.py 와 동일한 데이터·비용·복리 로직을 재사용(baseline 재현으로 검증).

각 팩터 결측 시 처리:
- 'none'  : 결측은 백분위에서 제외(현행 backtest.py 방식 — pct_rank None 유지)
- 'sector': 결측 팩터를 같은 업종 중위값으로 대입 후 백분위(업종평균 결측보정 실험)
"""
from __future__ import annotations
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

import statistics
import factor_config as cfg
import db
from factor.universe import build_master
from factor import data as D
from factor.backtest import (compute_universe, stock_return, _kospi_return,
                             pct_rank, rebal_date)
from factor.sectors import classify   # (industry, code) -> 섹터


FACTORS_BASE = ["ey", "by", "sy", "roe", "opm", "lowdebt"]


def build_sec_map(master):
    """code -> 섹터 (라이브 대시보드와 동일 classify 사용)."""
    m = {}
    for r in master.itertuples(index=False):
        try:
            m[r.code] = classify(getattr(r, "industry", None), r.code) or "기타"
        except Exception:
            m[r.code] = "기타"
    return m


def build_rows(conn, universe, fiscal_year, sec_map, with_growth=False):
    """유니버스 각 종목의 팩터 원값(+선택 성장성) 계산. score_universe 와 동일 규칙."""
    rows = []
    for u in universe:
        fin = D.financials_for_year(conn, u["code"], fiscal_year)
        if not fin:
            continue
        ni, eq, rev = fin["net_income"], fin["equity"], fin["revenue"]
        dr, om = fin["debt_ratio"], fin["op_margin"]
        mc = u["marcap"]
        if cfg.EXCLUDE_NEGATIVE_EARNINGS and (ni is None or ni <= 0):
            continue
        r = {
            **u,
            "ey": (ni / mc) if ni is not None else None,
            "by": (eq / mc) if eq is not None else None,
            "sy": (rev / mc) if rev is not None else None,
            "roe": (ni / eq) if (ni is not None and eq) else None,
            "opm": om,
            "lowdebt": (-dr) if dr is not None else None,
        }
        if with_growth:
            prev = D.financials_for_year(conn, u["code"], fiscal_year - 1)
            pr = prev["revenue"] if prev else None
            r["growth"] = ((rev / pr - 1) if (rev is not None and pr and pr > 0)
                           else None)
        r["_sec"] = sec_map.get(u["code"], "기타")
        rows.append(r)
    return rows


def _impute_sector(rows, keys):
    """결측 팩터를 같은 업종 중위값으로 대입(업종 결측 시 전체 중위값)."""
    for k in keys:
        vals_all = [r[k] for r in rows if r.get(k) is not None]
        gmed = statistics.median(vals_all) if vals_all else None
        by_sec = {}
        for r in rows:
            if r.get(k) is not None:
                by_sec.setdefault(r["_sec"], []).append(r[k])
        smed = {s: statistics.median(v) for s, v in by_sec.items() if v}
        for r in rows:
            if r.get(k) is None:
                r[k] = smed.get(r["_sec"], gmed)


def score_rows(rows, weights, missing="none"):
    """weights: {factor: w}. missing='sector'면 결측 업종중위 대입 후 채점.
    return: 점수순 정렬된 rows(사본 아님, r['_score'] 세팅)."""
    keys = list(weights.keys())
    if missing == "sector":
        _impute_sector(rows, keys)
    ranks = {k: pct_rank([r.get(k) for r in rows]) for k in keys}
    scored = []
    for i, r in enumerate(rows):
        s, wsum, valid = 0.0, 0.0, 0
        for k in keys:
            pr = ranks[k][i]
            if pr is not None:
                s += weights[k] * pr
                wsum += weights[k]
                valid += 1
        if valid >= cfg.MIN_VALID_FACTORS:
            r["_score"] = (s / wsum) if wsum else 0.0
            scored.append(r)
    scored.sort(key=lambda r: r["_score"], reverse=True)
    return scored


def precompute(conn, master, sec_map):
    """연도별 유니버스·팩터원값·주식수익률·벤치·코스피를 1회 계산."""
    years = list(range(cfg.BT_START_YEAR, cfg.BT_END_YEAR + 1))
    data = {}
    for y in years[:-1]:
        buy_d, sell_d = rebal_date(y), rebal_date(y + 1)
        universe = compute_universe(conn, master, y)
        fy = y - cfg.FISCAL_LAG
        rows = build_rows(conn, universe, fy, sec_map, with_growth=True)
        ret = {}
        for u in universe:
            ret[u["code"]] = stock_return(conn, u["code"], buy_d, sell_d, y)
        uni_codes = [u["code"] for u in universe]
        bench = [ret[c] for c in uni_codes if ret.get(c) is not None]
        bench_ret = (sum(bench) / len(bench)) if bench else None
        kospi = _kospi_return(buy_d, sell_d)
        data[y] = dict(rows=rows, ret=ret, uni_codes=uni_codes,
                       bench_ret=bench_ret, kospi=kospi)
        print(f"  {y}: 유니버스 {len(uni_codes)} · 재무보유 {len(rows)} · "
              f"벤치 {'—' if bench_ret is None else f'{bench_ret*100:+.1f}%'}",
              flush=True)
    return data


def run_config(data, name, weights, missing="none"):
    eq_s = eq_b = eq_k = 1.0
    per = []
    for y in sorted(data):
        d = data[y]
        if d["bench_ret"] is None:
            continue
        scored = score_rows(d["rows"], weights, missing)
        if not scored:
            continue
        picks = scored[:cfg.TOP_N]
        prets = [d["ret"][p["code"]] for p in picks
                 if d["ret"].get(p["code"]) is not None]
        if not prets:
            continue
        strat = sum(prets) / len(prets)
        eq_s *= (1 + strat)
        eq_b *= (1 + d["bench_ret"])
        if d["kospi"] is not None:
            eq_k *= (1 + d["kospi"])
        per.append({"y": y, "strat": strat, "bench": d["bench_ret"],
                    "excess": (strat - d["bench_ret"]) * 100})
    n = len(per)
    if not n:
        return None
    cagr_s = eq_s ** (1 / n) - 1
    cagr_b = eq_b ** (1 / n) - 1
    cagr_k = eq_k ** (1 / n) - 1
    wins = sum(1 for p in per if p["excess"] > 0)
    avg_ex = sum(p["excess"] for p in per) / n
    return dict(name=name, n=n, cagr_s=cagr_s, cagr_b=cagr_b, cagr_k=cagr_k,
                total_s=eq_s - 1, avg_ex=avg_ex, wins=wins,
                beat_uni=cagr_s > cagr_b, beat_kospi=cagr_s > cagr_k)


# ---- 가중치 조합 ----
W = dict  # alias
CONFIGS = [
    ("baseline(현행)",   dict(ey=1.0, by=1.0, sy=0.5, roe=1.0, opm=0.5, lowdebt=0.5), "none"),
    ("안정성강화",       dict(ey=1.0, by=1.0, sy=0.5, roe=1.0, opm=0.5, lowdebt=1.0), "none"),
    ("퀄리티+안정성",    dict(ey=1.0, by=1.0, sy=0.5, roe=1.0, opm=1.0, lowdebt=1.0), "none"),
    ("6팩터 동일가중",   dict(ey=1.0, by=1.0, sy=1.0, roe=1.0, opm=1.0, lowdebt=1.0), "none"),
    ("가치중심",         dict(ey=1.5, by=1.5, sy=1.0, roe=0.5, opm=0.5, lowdebt=0.5), "none"),
    ("성장성포함",       dict(ey=1.0, by=1.0, sy=0.5, roe=1.0, opm=0.5, lowdebt=0.5, growth=0.5), "none"),
    ("baseline+업종보정", dict(ey=1.0, by=1.0, sy=0.5, roe=1.0, opm=0.5, lowdebt=0.5), "sector"),
]


def main():
    conn = db.connect()
    print("master 로드…", flush=True)
    master = build_master()
    sec_map = build_sec_map(master)
    print("연도별 데이터 사전계산…", flush=True)
    data = precompute(conn, master, sec_map)

    print("\n" + "=" * 92)
    print(f"{'조합':<18}{'CAGR전략':>9}{'CAGR유니':>9}{'CAGR코스피':>10}"
          f"{'초과CAGR':>9}{'연평초과':>9}{'초과승률':>9}  판정")
    print("-" * 92)
    results = []
    for name, w, miss in CONFIGS:
        r = run_config(data, name, w, miss)
        if not r:
            print(f"{name:<18} (측정 실패)")
            continue
        results.append(r)
        verdict = ("유니O" if r["beat_uni"] else "유니X") + "/" + \
                  ("코스피O" if r["beat_kospi"] else "코스피X")
        print(f"{r['name']:<18}{r['cagr_s']*100:>+8.1f}%{r['cagr_b']*100:>+8.1f}%"
              f"{r['cagr_k']*100:>+9.1f}%{(r['cagr_s']-r['cagr_b'])*100:>+8.1f}%"
              f"{r['avg_ex']:>+8.1f}%{r['wins']:>6}/{r['n']}  {verdict}")
    print("=" * 92)
    if results:
        best = max(results, key=lambda r: (r["cagr_s"] - r["cagr_b"], r["cagr_s"]))
        print(f"\n>> 유니버스 대비 초과CAGR 최대: '{best['name']}' "
              f"(전략CAGR {best['cagr_s']*100:+.1f}%, 초과 {(best['cagr_s']-best['cagr_b'])*100:+.1f}%p)")
    conn.close()


if __name__ == "__main__":
    main()
