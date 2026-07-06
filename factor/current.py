# -*- coding: utf-8 -*-
"""현재 시점 가치+퀄리티 랭킹 계산 (대시보드용). 수집된 재무/가격 캐시 사용."""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import factor_config as cfg
import db
from factor.universe import build_master, eligible_at
from factor.backtest import pct_rank
from factor.sectors import classify


def _latest_close(conn, code):
    r = conn.execute(
        "SELECT close,date FROM daily_prices WHERE code=? AND close IS NOT NULL "
        "ORDER BY date DESC LIMIT 1", (code,)).fetchone()
    return (r[0], r[1]) if r else None


def _prev_close(conn, code, before_date):
    r = conn.execute(
        "SELECT close FROM daily_prices WHERE code=? AND close IS NOT NULL "
        "AND date<? ORDER BY date DESC LIMIT 1", (code, before_date)).fetchone()
    return r[0] if r else None


def _latest_financials(conn, code):
    r = conn.execute(
        "SELECT year,revenue,op_profit,net_income,assets,liabilities,equity,"
        "debt_ratio,op_margin FROM financials WHERE code=? ORDER BY year DESC LIMIT 1",
        (code,)).fetchone()
    if not r:
        return None
    keys = ["year", "revenue", "op_profit", "net_income", "assets",
            "liabilities", "equity", "debt_ratio", "op_margin"]
    return dict(zip(keys, r))


def _prior_financials(conn, code, before_year):
    """직전 연도 재무(성장률 계산용). 연속연도가 아니어도 그 다음으로 최신인 것."""
    r = conn.execute(
        "SELECT year,revenue,op_profit,net_income FROM financials "
        "WHERE code=? AND year<? ORDER BY year DESC LIMIT 1",
        (code, before_year)).fetchone()
    if not r:
        return None
    return {"year": r[0], "revenue": r[1], "op_profit": r[2], "net_income": r[3]}


def _growth_pct(cur, prev):
    if cur is None or prev is None or prev <= 0:
        return None
    return (cur / prev - 1) * 100


def compute_ranking(conn, master=None, asof=None):
    """현재 유니버스의 가치+퀄리티 점수 랭킹."""
    if master is None:
        master = build_master()
    if asof is None:
        row = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()
        asof = row[0] or "2026-07-01"

    elig = eligible_at(master, asof, cfg)
    rows = []
    for r in elig.itertuples(index=False):
        if r.shares is None:
            continue
        p = _latest_close(conn, r.code)
        if not p:
            continue
        marcap = r.shares * p[0]
        if marcap < cfg.MIN_MARKET_CAP:
            continue
        fin = _latest_financials(conn, r.code)
        if not fin:
            continue
        ni, eq, rev, op = fin["net_income"], fin["equity"], fin["revenue"], fin["op_profit"]
        om, dr = fin["op_margin"], fin["debt_ratio"]
        if cfg.EXCLUDE_NEGATIVE_EARNINGS and (ni is None or ni <= 0):
            continue
        prev = _prev_close(conn, r.code, p[1])
        chg_pct = ((p[0] / prev - 1) * 100) if prev else None
        dps = db.get_dividend(conn, r.code, fin["year"])
        div_yield = (dps / p[0] * 100) if dps else None
        pf = _prior_financials(conn, r.code, fin["year"])
        rev_growth = _growth_pct(rev, pf["revenue"]) if pf else None
        op_growth = _growth_pct(op, pf["op_profit"]) if pf else None
        rows.append({
            "code": r.code, "name": r.name, "market": r.market,
            "sector": classify(getattr(r, "industry", None)),
            "industry": getattr(r, "industry", None),
            "price": p[0], "price_date": p[1], "chg_pct": chg_pct, "marcap": marcap,
            "fiscal_year": fin["year"], "fin": fin,
            "revenue": rev, "op_profit": op, "net_income": ni,
            "div_yield": div_yield, "rev_growth": rev_growth, "op_growth": op_growth,
            "per": (marcap / ni) if ni else None,
            "pbr": (marcap / eq) if eq else None,
            "psr": (marcap / rev) if rev else None,
            "roe": (ni / eq * 100) if (ni is not None and eq) else None,
            "op_margin": om, "debt_ratio": dr,
            "_ey": (ni / marcap) if ni is not None else None,
            "_by": (eq / marcap) if eq is not None else None,
            "_sy": (rev / marcap) if rev is not None else None,
            "_roe": (ni / eq) if (ni is not None and eq) else None,
            "_opm": om,
            "_lowdebt": (-dr) if dr is not None else None,
            "_growth": rev_growth,
        })
    if not rows:
        return []

    # 백테스트로 검증된 종합점수(6팩터)는 그대로 유지 — growth는 여기 섞지 않음
    factors = [("_ey", cfg.W_EARNINGS_YIELD), ("_by", cfg.W_BOOK_YIELD),
               ("_sy", cfg.W_SALES_YIELD), ("_roe", cfg.W_ROE),
               ("_opm", cfg.W_OP_MARGIN), ("_lowdebt", cfg.W_LOW_DEBT)]
    ranks = {k: pct_rank([r[k] for r in rows]) for k, _ in factors}
    growth_ranks = pct_rank([r["_growth"] for r in rows])   # 표시용 별도 백분위
    for i, r in enumerate(rows):
        s, wsum, valid = 0.0, 0.0, 0
        breakdown = {}
        for k, w in factors:
            pr = ranks[k][i]
            breakdown[k] = pr
            if pr is not None:
                s += w * pr
                wsum += w
                valid += 1
        r["valid"] = valid
        r["score"] = round((s / wsum) * 100, 1) if wsum else 0.0
        breakdown["_growth"] = growth_ranks[i]
        r["breakdown"] = {k: (round(v, 2) if v is not None else None)
                          for k, v in breakdown.items()}
    rows = [r for r in rows if r["valid"] >= cfg.MIN_VALID_FACTORS]
    rows.sort(key=lambda r: r["score"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    from factor.interpret import dimension_grades, sector_averages
    sec_avg = sector_averages(rows)
    for r in rows:
        r["dims"] = dimension_grades(r, sec_avg)
    return rows


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    conn = db.connect()
    rk = compute_ranking(conn)
    print(f"랭킹 종목 수: {len(rk)}")
    print(f"{'#':>3} {'코드':>6} {'종목명':<12} {'점수':>5} {'PER':>6} "
          f"{'PBR':>5} {'ROE%':>6} {'부채%':>6}")
    for r in rk[:15]:
        print(f"{r['rank']:>3} {r['code']:>6} {str(r['name'])[:12]:<12} "
              f"{r['score']:>5} {(r['per'] or 0):>6.1f} {(r['pbr'] or 0):>5.2f} "
              f"{(r['roe'] or 0):>6.1f} {(r['debt_ratio'] or 0):>6.0f}")
    conn.close()
