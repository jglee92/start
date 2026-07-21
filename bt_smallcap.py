# -*- coding: utf-8 -*-
"""
소형주(시총 300억~3,000억) 전용 가치+퀄리티 팩터 백테스트 — 별도 검증용.

기존 factor/backtest.py(factor_config.py 시총 3,000억 이상 검증, 사이트에 게시된
+3%p 클레임의 근거)는 그대로 두고, 그 미만 구간만 같은 방법론(시점정합·상장폐지
포함·거래비용·배당 반영)으로 별도 검증한다.
통과하면(전략이 소형주 유니버스 평균을 이기면) 사이트의 "참고용·백테스트 미검증"
라벨을 뗄 근거가 되고, 통과 못하면 계속 참고용으로 남긴다.

사용: .\.venv\Scripts\python.exe bt_smallcap.py
"""
from __future__ import annotations
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import factor_config as cfg
import db
from factor.universe import build_master, eligible_at
from factor import data as D
from factor.backtest import rebal_date, score_universe, ew_return, kospi_above_ma, _kospi_return

MIN_MARKET_CAP_SMALL = cfg.MIN_MARKET_CAP_VALIDATED   # 300억 하한(극소형 잡주 제외)
MAX_MARKET_CAP_SMALL = cfg.MIN_MARKET_CAP    # 3,000억 상한(기존 검증 구간과 안 겹침)
# 200/년 — 매일 밤 도는 전종목 분기재무 백필(daily-fundamentals.yml)과 DART
# 일일한도(2만건)를 나눠 써야 해서, 한 번에 하루 한도를 다 쓰지 않게 낮춰둠.
MAX_UNIVERSE_PER_YEAR_SMALL = 200


def compute_universe_small(conn, master, year):
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
        if marcap < MIN_MARKET_CAP_SMALL or marcap >= MAX_MARKET_CAP_SMALL:
            continue
        recs.append({"code": r.code, "name": r.name, "market": r.market,
                     "delisting_date": r.delisting_date, "marcap": marcap})
    recs.sort(key=lambda x: x["marcap"], reverse=True)
    return recs[:MAX_UNIVERSE_PER_YEAR_SMALL]


def main():
    conn = db.connect()
    master = build_master()
    years = list(range(cfg.BT_START_YEAR, cfg.BT_END_YEAR + 1))

    # 1) 가격 수집: 모든 리밸 시점 유니버스 후보(상폐포함) 합집합
    cand = set()
    for y in years:
        for r in eligible_at(master, rebal_date(y), cfg).itertuples(index=False):
            cand.add(r.code)
    print(f"가격 후보 {len(cand)}종목 (상폐포함, 시총필터 前)", flush=True)
    D.ensure_prices(conn, sorted(cand),
                    f"{cfg.BT_START_YEAR-2}-01-01", f"{cfg.BT_END_YEAR+1}-07-01")

    # 2) 연도별 소형주 유니버스 확정 + 재무 수집 대상
    universes = {}
    fin_pairs = []
    for y in years:
        u = compute_universe_small(conn, master, y)
        universes[y] = u
        fy = y - cfg.FISCAL_LAG
        fin_pairs += [(x["code"], fy) for x in u]
    print(f"소형주 유니버스(연도별): {[len(universes[y]) for y in years]}", flush=True)
    print(f"재무 대상 {len(fin_pairs)}쌍 (연도별 유니버스 합)", flush=True)
    from dart_client import DartClient
    dart = DartClient(os.getenv("DART_API_KEY"))
    dart.corp_map()
    D.ensure_financials(dart, conn, fin_pairs)

    if cfg.INCLUDE_DIVIDENDS:
        div_pairs = []
        for y in years[:-1]:
            div_pairs += [(x["code"], y) for x in universes[y]]
        D.ensure_dividends(dart, conn, div_pairs)

    # 3) 리밸런싱 루프 (factor/backtest.py의 score_universe/ew_return 재사용 —
    #    동일 팩터식·동일 비용가정으로 비교 가능하게)
    print("\n" + "=" * 84)
    print("소형주(300억~3,000억) 가치+퀄리티 팩터 백테스트 — 참고용 라벨 검증")
    print(f"유니버스: {cfg.MARKETS} 시총 {MIN_MARKET_CAP_SMALL/1e8:.0f}~{MAX_MARKET_CAP_SMALL/1e8:.0f}억 "
          f"상위{MAX_UNIVERSE_PER_YEAR_SMALL} · 보유 상위{cfg.TOP_N} 동일가중 · 왕복비용 "
          f"{(cfg.FEE_RATE*2+cfg.SELL_TAX+cfg.SLIPPAGE*2)*100:.2f}%")
    print("=" * 84)
    print(f"{'리밸년':>6} {'유니버스':>7} {'선택':>4} {'전략수익%':>9} "
          f"{'유니버스EW%':>10} {'초과%p':>7} {'코스피%':>8}")
    print("-" * 84)

    eq_strat, eq_bench, eq_kospi = 1.0, 1.0, 1.0
    per_year = []
    for y in years[:-1]:
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
            strat_ret = 0.0
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

    _summary_small(per_year, eq_strat, eq_bench, eq_kospi)
    conn.close()


def _summary_small(per_year, eq_strat, eq_bench, eq_kospi):
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
    print(f"\n  >> 소형주 구간에서도 팩터가 유니버스 평균을 이기는가: "
          f"{'예(CAGR 기준)' if cagr_s > cagr_b else '아니오'}")
    print(f"  >> 시장(코스피) 대비: {'초과' if cagr_s > cagr_k else '미달'}")
    div = "포함(세후)" if cfg.INCLUDE_DIVIDENDS else "미반영"
    print(f"\n한계: 과거 주식수 미확보→marcap 근사 · 시총 300~3,000억 구간(그 이상은 "
          f"별도 검증된 factor/backtest.py 참고) · 폐지 종목은 마지막체결가로 청산 "
          f"(청산가치 過大 가능) · 배당 {div}.")


if __name__ == "__main__":
    main()
