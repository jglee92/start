# -*- coding: utf-8 -*-
"""
현재 대시보드 유니버스의 재무/배당을 '최신 회계연도'로 갱신.

DART 사업보고서는 매년 3월말 공시되므로, 연중이면 전년도(예: 2026년 → FY2025)가 있다.
팩터 백테스트 수집은 시점정합상 과거 연도까지만 받으므로, 대시보드 최신성을 위해
여기서 최신 FY를 따로 채운다.

사용: .\.venv\Scripts\python.exe refresh_fundamentals.py
"""
from __future__ import annotations
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import factor_config as cfg
import db
from factor.universe import build_master, eligible_at
from factor.data import price_asof
from dart_client import DartClient, DartError

LATEST_FY = datetime.now().year - 1   # 2026 → FY2025


def main():
    conn = db.connect()
    master = build_master()
    asof = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
    elig = eligible_at(master, asof, cfg)

    # 시총 필터로 대시보드 유니버스만 추림
    codes = []
    for r in elig.itertuples(index=False):
        if r.shares is None:
            continue
        p = price_asof(conn, r.code, asof)
        if p and r.shares * p[0] >= cfg.MIN_MARKET_CAP:
            codes.append(r.code)
    print(f"유니버스 {len(codes)}종목 · FY{LATEST_FY} 재무/배당 갱신", flush=True)

    dart = DartClient(os.getenv("DART_API_KEY"))
    dart.corp_map()
    fin_got = div_got = audit_got = 0
    for i, code in enumerate(codes, 1):
        # 재무: 이미 FY_LATEST 있으면 skip
        has = conn.execute("SELECT 1 FROM financials WHERE code=? AND year=?",
                           (code, LATEST_FY)).fetchone()
        if not has:
            try:
                fin = dart.get_financials(code, year=LATEST_FY)
            except DartError as e:
                print(f"[중단] {e}"); break
            except Exception:
                fin = None
            if fin:
                db.save_financials(conn, code, fin); fin_got += 1
        # 배당
        if db.get_dividend(conn, code, LATEST_FY) is None:
            try:
                dps = dart.get_dividend_dps(code, LATEST_FY)
            except Exception:
                dps = None
            db.save_dividend(conn, code, LATEST_FY, dps if dps is not None else 0.0)
            div_got += 1
        # 감사의견
        if db.get_audit_opinion(conn, code, LATEST_FY) is None:
            try:
                op = dart.get_audit_opinion(code, LATEST_FY)
            except DartError as e:
                print(f"[중단] {e}"); break
            except Exception:
                op = None
            if op:
                db.save_audit_opinion(conn, code, LATEST_FY, op["auditor"], op["opinion"])
                audit_got += 1
        if i % 50 == 0:
            print(f"  ...{i}/{len(codes)} (재무 {fin_got}, 배당 {div_got}, 감사의견 {audit_got})", flush=True)

    conn.close()
    print(f"완료. FY{LATEST_FY} 재무 {fin_got}건, 배당 {div_got}건, 감사의견 {audit_got}건 갱신.")
    print("→ 대시보드 /api/refresh 호출 또는 서버 재시작 시 반영.")


if __name__ == "__main__":
    main()
