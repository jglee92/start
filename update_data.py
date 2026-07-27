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
import os
import sys
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8")

import db
from factor.data import _fetch_one

REFRESH_TAIL_DAYS = 10   # 최근 며칠 재조회(겹침은 INSERT OR REPLACE 로 갱신)
# 배포용 슬림 DB(screener_deploy.db)는 2026-07 실제로 GitHub 파일당 100MB 제한에
# 걸려 매일 push가 조용히 거부되던 걸 발견함(원인 파악에 5일 걸림 — 블로그/카드
# 생성은 계속 "성공"으로 떴지만 실제로는 마지막으로 push된 옛 시세를 그대로 씀).
# 그래서 배포 DB에 한해서만(로컬 원본 screener.db는 절대 안 건드림 — 백테스트가
# 전체 히스토리를 요구) 매일 갱신 뒤 오래된 행을 지워 파일 크기를 일정하게 유지한다.
RETENTION_DAYS = 730   # app.py 차트 조회창(2년)과 동일하게 맞춤


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

    is_deploy_db = "screener_deploy" in os.path.basename(db.DB_PATH)
    if is_deploy_db:
        cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
        deleted = conn.execute("DELETE FROM daily_prices WHERE date<?", (cutoff,)).rowcount
        conn.commit()
        if deleted:
            print(f"보존기간({RETENTION_DAYS}일) 초과 {deleted:,}행 삭제 (배포 DB 크기 관리)", flush=True)

    mx = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
    conn.close()
    print(f"완료. 갱신 {upd}종목 · 최신 가격일 {mx}", flush=True)
    print("→ 대시보드 서버를 재시작하면 최신 랭킹이 반영됩니다.")


if __name__ == "__main__":
    main()
