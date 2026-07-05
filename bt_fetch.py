# -*- coding: utf-8 -*-
"""
백테스트용 히스토리 수집.

현재 유니버스(보통주 · 시총밴드 · 유동성) 상위 N종목의 과거 일봉을
daily_prices 테이블에 적재한다. 재실행 시 이미 받은 종목은 건너뛴다(캐시).

주의: 유니버스를 '오늘 기준'으로 잡으므로 생존편향이 있다(상장폐지된 종목 누락).
      v1 백테스트의 알려진 한계로, 결과는 '낙관 편향'일 수 있다.
"""
from __future__ import annotations
import os
import sys
import time
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8")

import config as cfg
import db
from providers import get_provider


def build_universe():
    provider = get_provider(cfg.DATA_PROVIDER)
    snap = provider.get_market_snapshot()
    df = snap.df
    m = df["market"].isin(cfg.MARKETS)
    if cfg.COMMON_STOCK_ONLY:
        m &= df["code"].astype(str).str.endswith("0")
    m &= df["amount"] >= cfg.MIN_TRADING_VALUE
    m &= df["marcap"] >= cfg.MIN_MARKET_CAP
    if cfg.MAX_MARKET_CAP is not None:
        m &= df["marcap"] <= cfg.MAX_MARKET_CAP
    for kw in cfg.NAME_EXCLUDE_KEYWORDS:
        m &= ~df["name"].astype(str).str.contains(kw, regex=False)
    uni = df[m].sort_values("marcap", ascending=False).head(cfg.BACKTEST_MAX_TICKERS)
    return provider, uni[["code", "name"]].reset_index(drop=True)


def main():
    provider, uni = build_universe()
    conn = db.connect()
    print(f"유니버스 {len(uni)}종목 · 히스토리 {cfg.BACKTEST_LOOKBACK_DAYS}일 수집")

    # 이미 충분히 캐시된 종목은 skip (거래일 300개 이상 있으면 통과로 간주)
    done = 0
    for i, row in uni.iterrows():
        code = row["code"]
        cur = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE code=?", (code,)).fetchone()[0]
        if cur >= 300:
            done += 1
            continue
        h = provider.get_history(code, cfg.BACKTEST_LOOKBACK_DAYS)
        if h is not None and len(h):
            db.cache_history(conn, code, h)
            done += 1
        if (i + 1) % 25 == 0:
            print(f"  ...{i+1}/{len(uni)} (적재 {done})")
        time.sleep(0.05)  # 서버 예의

    total = conn.execute("SELECT COUNT(DISTINCT code) FROM daily_prices").fetchone()[0]
    rows = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
    conn.close()
    print(f"완료. daily_prices: {total}종목 · {rows:,}행")


if __name__ == "__main__":
    main()
