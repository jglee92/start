# -*- coding: utf-8 -*-
"""
일일 데이터 갱신.

데이터는 '리셋'되지 않고 SQLite(data/screener.db)에 영구 저장된다. 다만 자동
최신화는 안 되므로, 이 스크립트로 최근 가격을 덧붙인다(증분). 재무/배당은 연 1회
공시되므로 매일 받을 필요 없음(연초에 factor.backtest 재실행 시 새 연도 수집).

사용: .\.venv\Scripts\python.exe update_data.py
      (이후 대시보드 서버 재시작하면 최신 랭킹 반영)
"""
from __future__ import annotations
import sys
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8")

import db
from factor.data import _fetch_one

REFRESH_TAIL_DAYS = 10   # 최근 며칠 재조회(겹침은 INSERT OR REPLACE 로 갱신)


def main():
    conn = db.connect()
    codes = [r[0] for r in conn.execute(
        "SELECT DISTINCT code FROM daily_prices").fetchall()]
    today = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=REFRESH_TAIL_DAYS)).strftime("%Y-%m-%d")
    print(f"가격 증분 갱신: {len(codes)}종목 · {start}~{today}", flush=True)

    ex = ThreadPoolExecutor(max_workers=12)
    futures = [(c, ex.submit(_fetch_one, c, start, today)) for c in codes]
    upd = 0
    for i, (c, fut) in enumerate(futures, 1):
        try:
            df = fut.result(timeout=25)
        except Exception:
            df = None
        if df is not None and len(df):
            db.cache_history(conn, c, df)
            upd += 1
        if i % 300 == 0:
            print(f"  ...{i}/{len(codes)} (갱신 {upd})", flush=True)
    ex.shutdown(wait=False, cancel_futures=True)

    mx = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
    conn.close()
    print(f"완료. 갱신 {upd}종목 · 최신 가격일 {mx}", flush=True)
    print("→ 대시보드 서버를 재시작하면 최신 랭킹이 반영됩니다.")


if __name__ == "__main__":
    main()
