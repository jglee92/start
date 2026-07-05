# -*- coding: utf-8 -*-
"""
가치+퀄리티 팩터 백테스트 (저회전·연1회·시점정합·상폐포함).

- 유니버스: 각 5월6일 시점에 실제 상장돼 있던 종목(상폐 포함) 중 시총 상위.
- 팩터: 가치(이익/장부/매출 수익률) + 퀄리티(ROE/영업이익률/저부채), 유니버스내 백분위 가중합.
- 매수: 리밸일 최초 체결가 / 매도: 다음 리밸일(또는 폐지 직전) 종가. 비용 차감.
- 벤치마크: 동일가중 유니버스(팩터선택X) + 코스피(KS11).
"""
from __future__ import annotations
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

import factor_config as cfg
import db
from factor.universe import build_master, eligible_at
from factor import data as D


def rebal_date(year):
    return f"{year}-{cfg.REBAL_MONTH:02d}-{cfg.REBAL_DAY:02d}"


def pct_rank(values):
    """값 리스트 → 백분위(0~1) 리스트. None 은 None 유지(해당 팩터 미반영)."""
    idx = [i for i, v in enumerate(values) if v is not None]
    out = [None] * len(values)
    if len(idx) <= 1:
        for i in idx:
            out[i] = 0.5
        return out
    order = sorted(idx, key=lambda i: values[i])
    for rank, i in enumerate(order):
        out[i] = rank / (len(idx) - 1)
    return out


def compute_universe(conn, master, year):
    """year 리밸 시점 유니버스(시총필터+상위N) + marcap 반환."""
    date = rebal_date(year)
    elig = eligible_at(master, date, cfg)
    recs = []
    for r in elig.itertuples(index=False):
        if r.shares is None:
            continue
        p = D.price_asof(conn, r.code, date)
        if not p:
            continue
        marcap = r.shares * p[0]
        if marcap < cfg.MIN_MARKET_CAP:
            continue
        recs.append({"code": r.code, "name": r.name, "market": r.market,
                     "delisting_date": r.delisting_date, "marcap": marcap})
    recs.sort(key=lambda x: x["marcap"], reverse=True)
    return recs[:cfg.MAX_UNIVERSE_PER_YEAR]


def score_universe(conn, universe, fiscal_year):
    """유니버스 각 종목에 팩터·스코어 부여. 재무 없는/적자 종목 처리."""
    rows = []
    for u in universe:
        fin = D.financials_for_year(conn, u["code"], fiscal_year)
        if not fin:
            continue
        ni, eq, rev = fin["net_income"], fin["equity"], fin["revenue"]
        op, dr, om = fin["op_profit"], fin["debt_ratio"], fin["op_margin"]
        mc = u["marcap"]
        if cfg.EXCLUDE_NEGATIVE_EARNINGS and (ni is None or ni <= 0):
            continue
        rows.append({
            **u,
            "ey": (ni / mc) if ni is not None else None,          # 이익수익률
            "by": (eq / mc) if eq is not None else None,          # 장부수익률(1/PBR)
            "sy": (rev / mc) if rev is not None else None,        # 매출수익률
            "roe": (ni / eq) if (ni is not None and eq) else None,
            "opm": om,
            "lowdebt": (-dr) if dr is not None else None,
        })
    if not rows:
        return []

    factors = [("ey", cfg.W_EARNINGS_YIELD), ("by", cfg.W_BOOK_YIELD),
               ("sy", cfg.W_SALES_YIELD), ("roe", cfg.W_ROE),
               ("opm", cfg.W_OP_MARGIN), ("lowdebt", cfg.W_LOW_DEBT)]
    ranks = {k: pct_rank([r[k] for r in rows]) for k, _ in factors}
    for i, r in enumerate(rows):
        s, wsum, valid = 0.0, 0.0, 0
        for k, w in factors:
            pr = ranks[k][i]
            if pr is not None:
                s += w * pr
                wsum += w
                valid += 1
        r["valid"] = valid
        r["score"] = (s / wsum) if wsum else 0.0
    rows = [r for r in rows if r["valid"] >= cfg.MIN_VALID_FACTORS]
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


RT_BUY = 1 + cfg.SLIPPAGE + cfg.FEE_RATE
RT_SELL = 1 - cfg.SLIPPAGE - cfg.FEE_RATE - cfg.SELL_TAX


DIV_TAX = 0.154   # 배당소득세 15.4%


def stock_return(conn, code, buy_date, sell_date, div_year=None):
    """매수일 최초체결가 → 매도일(또는 폐지직전) 종가, 비용 반영 net 수익률.
    div_year 주면 그 회계연도 현금배당(세후)을 총수익에 가산."""
    b = D.price_first_after(conn, code, buy_date)
    if not b:
        return None
    s = D.price_asof(conn, code, sell_date)
    if not s or s[1] < b[1]:      # 매도가가 매수일 이전이면 무효
        return None
    buy = b[0] * RT_BUY
    sell = s[0] * RT_SELL
    ret = sell / buy - 1
    if cfg.INCLUDE_DIVIDENDS and div_year is not None:
        dps = db.get_dividend(conn, code, div_year)
        if dps:
            ret += (dps * (1 - DIV_TAX)) / b[0]   # 세후 배당수익률 가산
    return ret


def ew_return(conn, codes, buy_date, sell_date, div_year=None):
    rets = [stock_return(conn, c, buy_date, sell_date, div_year) for c in codes]
    rets = [r for r in rets if r is not None]
    return (sum(rets) / len(rets), len(rets)) if rets else (None, 0)


def kospi_above_ma(buy_date):
    """리밸일에 코스피가 REGIME_MA_DAYS 이평선 위인가? (True=투자, False=현금)"""
    try:
        import FinanceDataReader as fdr
        from datetime import datetime, timedelta
        start = (datetime.fromisoformat(buy_date) -
                 timedelta(days=cfg.REGIME_MA_DAYS * 2)).strftime("%Y-%m-%d")
        h = fdr.DataReader("KS11", start, buy_date)
        if h is None or len(h) < cfg.REGIME_MA_DAYS:
            return True
        ma = h["Close"].tail(cfg.REGIME_MA_DAYS).mean()
        return h["Close"].iloc[-1] >= ma
    except Exception:
        return True


def main():
    conn = db.connect()
    master = build_master()
    years = list(range(cfg.BT_START_YEAR, cfg.BT_END_YEAR + 1))

    # 1) 가격 수집: 모든 리밸 시점 유니버스 후보(상폐포함) 합집합
    cand = set()
    for y in years:
        for r in eligible_at(master, rebal_date(y), cfg).itertuples(index=False):
            cand.add(r.code)
    print(f"가격 후보 {len(cand)}종목 (상폐포함, 시총필터 前)")
    D.ensure_prices(conn, sorted(cand),
                    f"{cfg.BT_START_YEAR-2}-01-01", f"{cfg.BT_END_YEAR+1}-07-01")

    # 2) 연도별 유니버스 확정 + 재무 수집 대상
    universes = {}
    fin_pairs = []
    for y in years:
        u = compute_universe(conn, master, y)
        universes[y] = u
        fy = y - cfg.FISCAL_LAG
        fin_pairs += [(x["code"], fy) for x in u]
    print(f"재무 대상 {len(fin_pairs)}쌍 (연도별 유니버스 합)")
    from dart_client import DartClient
    dart = DartClient(os.getenv("DART_API_KEY"))
    dart.corp_map()
    D.ensure_financials(dart, conn, fin_pairs)

    # 배당 수집: 보유연도 Y 의 현금배당(ex-date Dec Y, 보유 May Y~May Y+1 중 수령)
    if cfg.INCLUDE_DIVIDENDS:
        div_pairs = []
        for y in years[:-1]:
            div_pairs += [(x["code"], y) for x in universes[y]]
        D.ensure_dividends(dart, conn, div_pairs)

    # 3) 리밸런싱 루프
    print("\n" + "=" * 84)
    print("가치+퀄리티 팩터 백테스트 (연1회·시점정합·상폐포함)")
    print(f"유니버스: {cfg.MARKETS} 시총≥{cfg.MIN_MARKET_CAP/1e8:.0f}억 상위{cfg.MAX_UNIVERSE_PER_YEAR} · "
          f"보유 상위{cfg.TOP_N} 동일가중 · 왕복비용 "
          f"{(cfg.FEE_RATE*2+cfg.SELL_TAX+cfg.SLIPPAGE*2)*100:.2f}%")
    print(f"레버: 배당포함={cfg.INCLUDE_DIVIDENDS}(세후) · 시장국면필터={cfg.REGIME_FILTER}"
          f"(코스피 {cfg.REGIME_MA_DAYS}일선)")
    print("=" * 84)
    print(f"{'리밸년':>6} {'유니버스':>7} {'선택':>4} {'전략수익%':>9} "
          f"{'유니버스EW%':>10} {'초과%p':>7} {'코스피%':>8}")
    print("-" * 84)

    eq_strat, eq_bench, eq_kospi = 1.0, 1.0, 1.0
    per_year = []
    for y in years[:-1]:            # 마지막 해는 다음해 수익 측정 위해 제외
        buy_d, sell_d = rebal_date(y), rebal_date(y + 1)
        scored = score_universe(conn, universes[y], y - cfg.FISCAL_LAG)
        if not scored:
            print(f"{y:>6}  (재무 부족으로 건너뜀)")
            continue
        picks = scored[:cfg.TOP_N]
        strat_ret, ns = ew_return(conn, [p["code"] for p in picks], buy_d, sell_d, y)
        uni_codes = [u["code"] for u in universes[y]]
        bench_ret, nb = ew_return(conn, uni_codes, buy_d, sell_d, y)
        kospi = _kospi_return(buy_d, sell_d)

        if strat_ret is None or bench_ret is None:
            continue

        cash = False
        if cfg.REGIME_FILTER and not kospi_above_ma(buy_d):
            strat_ret = 0.0            # 현금 회피
            cash = True
        eq_strat *= (1 + strat_ret)
        eq_bench *= (1 + bench_ret)
        if kospi is not None:
            eq_kospi *= (1 + kospi)
        excess = (strat_ret - bench_ret) * 100
        per_year.append({"y": y, "strat": strat_ret, "bench": bench_ret,
                         "kospi": kospi, "excess": excess})
        print(f"{y:>6} {len(uni_codes):>7} {len(picks):>4} {strat_ret*100:>+8.1f} "
              f"{bench_ret*100:>+9.1f} {excess:>+7.1f} "
              f"{(kospi*100 if kospi is not None else float('nan')):>+7.1f}"
              f"{'  [현금]' if cash else ''}")

    _summary(per_year, eq_strat, eq_bench, eq_kospi)
    conn.close()


def _kospi_return(buy_d, sell_d):
    try:
        import FinanceDataReader as fdr
        h = fdr.DataReader("KS11", buy_d, sell_d)
        if h is None or len(h) < 2:
            return None
        return h["Close"].iloc[-1] / h["Close"].iloc[0] - 1
    except Exception:
        return None


def _summary(per_year, eq_strat, eq_bench, eq_kospi):
    if not per_year:
        print("\n(측정된 연도 없음 — 데이터 수집 상태 확인)")
        return
    n = len(per_year)
    cagr_s = eq_strat ** (1 / n) - 1
    cagr_b = eq_bench ** (1 / n) - 1
    cagr_k = eq_kospi ** (1 / n) - 1
    wins = sum(1 for p in per_year if p["excess"] > 0)
    print("-" * 84)
    print(f"\n[누적 {n}년]")
    print(f"  전략      : 총 {(eq_strat-1)*100:+.1f}%  · CAGR {cagr_s*100:+.1f}%")
    print(f"  유니버스EW: 총 {(eq_bench-1)*100:+.1f}%  · CAGR {cagr_b*100:+.1f}%")
    print(f"  코스피    : 총 {(eq_kospi-1)*100:+.1f}%  · CAGR {cagr_k*100:+.1f}%")
    print(f"  연평균 초과(vs 유니버스EW): {sum(p['excess'] for p in per_year)/n:+.1f}%p"
          f" · 초과승률 {wins}/{n}")
    print(f"\n  >> 팩터가 유니버스 평균을 이기는가: "
          f"{'예(CAGR 기준)' if cagr_s > cagr_b else '아니오'}")
    print(f"  >> 시장(코스피) 대비: {'초과' if cagr_s > cagr_k else '미달'}")
    div = "포함(세후)" if cfg.INCLUDE_DIVIDENDS else "미반영"
    print(f"\n한계: 과거 주식수 미확보→marcap 근사 · 시총 3000억↑만(소형가치 제외) · "
          f"폐지 종목은 마지막체결가로 청산(청산가치 過大 가능) · 배당 {div}.")


if __name__ == "__main__":
    main()
