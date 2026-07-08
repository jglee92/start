# -*- coding: utf-8 -*-
"""
전체 대시보드 유니버스의 표준분기(단독) 재무 + 정확한 공시일을 수집해
quarterly_financials에 저장한다. 최근 2개 회계연도(최대 8분기)만 대상 —
분기별 재무표/이상신호 기능 표시용(전체 기간 리서치는 backfill_quarterly_pilot.py 참고).

DART 하루 쿼터(20,000건) 고려해 종목당 최대 8분기*2호출(재무+공시일)=16건 —
전체 유니버스(~450개) 기준 최대 7,200건 정도로 여유 있음.

사용: KR_DB_PATH=data/screener_deploy.db .\.venv\Scripts\python.exe backfill_quarterly_full.py
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
from factor.pead import standalone_from_cumulative, REPRT

THIS_YEAR = datetime.now().year
YEARS = [THIS_YEAR - 1, THIS_YEAR]   # 최근 2개 연도 = 최대 8분기


def main():
    conn = db.connect()
    master = build_master()
    asof = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
    elig = eligible_at(master, asof, cfg)

    codes = []
    for r in elig.itertuples(index=False):
        if r.shares is None:
            continue
        p = price_asof(conn, r.code, asof)
        if p and r.shares * p[0] >= cfg.MIN_MARKET_CAP:
            codes.append(r.code)
    print(f"유니버스 {len(codes)}종목 · {YEARS} 분기재무 백필", flush=True)

    dart = DartClient(os.getenv("DART_API_KEY"))
    dart.corp_map()

    fin_got = date_got = 0
    for ci, code in enumerate(codes, 1):
        for y in YEARS:
            # 이미 4분기 다 있으면 스킵(증분)
            have = sum(1 for q in (1, 2, 3, 4) if db.get_quarterly(conn, code, y, q))
            if have == 4:
                continue
            cum = {}
            for q, reprt in REPRT.items():
                try:
                    fin = dart.get_period_financials(code, y, reprt)
                except DartError as e:
                    print(f"[중단] {code} {y}Q{q}: {e}")
                    conn.close()
                    print(f"\n중단 시점까지: 표준분기 {fin_got}건 저장(공시일 {date_got}건).")
                    return
                except Exception:
                    fin = None
                cum[q] = fin
            standalone = standalone_from_cumulative(cum[1], cum[2], cum[3], cum[4])

            for q in (1, 2, 3, 4):
                s = standalone.get(q)
                if not s or s.get("net_income") is None:
                    continue
                if db.get_quarterly(conn, code, y, q):
                    continue
                try:
                    ddate = dart.get_report_date(code, y, REPRT[q])
                except DartError as e:
                    print(f"[중단] {code} {y}Q{q} date: {e}")
                    conn.close()
                    print(f"\n중단 시점까지: 표준분기 {fin_got}건 저장(공시일 {date_got}건).")
                    return
                except Exception:
                    ddate = None
                db.save_quarterly(conn, code, y, q, s.get("revenue"), s.get("op_profit"),
                                  s.get("net_income"), ddate,
                                  debt_ratio=s.get("debt_ratio"), op_margin=s.get("op_margin"))
                fin_got += 1
                if ddate:
                    date_got += 1
        if ci % 20 == 0:
            print(f"  ...{ci}/{len(codes)} (표준분기 {fin_got}건, 공시일 {date_got}건)", flush=True)

    conn.close()
    print(f"\n완료. 표준분기 {fin_got}건 저장(공시일 확보 {date_got}건).")


if __name__ == "__main__":
    main()
