# -*- coding: utf-8 -*-
"""
PEAD 리서치 본채집: 파일럿(backfill_quarterly_pilot.py, 대형주 40개)에서 확장해
전체 대시보드 유니버스(시총 3,000억↑)의 표준분기(단독) 재무 + 정확한 공시일을
2020~2025년 전체 구간으로 수집한다. factor/pead_backtest.py 재실행용.

로컬 전체 DB(data/screener.db, gitignored)에만 저장 — 배포용 슬림 DB나 git과 무관.

DART 하루 쿼터(20,000건) 고려: 종목당 최대 24분기*2호출(재무+공시일)=48건.
전체 유니버스(~450개) 기준 최대 21,600건으로 하루 쿼터를 넘을 수 있음 —
쿼터 초과 시 자동 중단하며, 이미 받은 분기는 스킵하므로 다음날 재실행하면
이어서 채운다(증분).

사용: .\.venv\Scripts\python.exe backfill_quarterly_pead_full.py
"""
from __future__ import annotations
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import factor_config as cfg
import db
from factor.universe import build_master, eligible_at
from factor.data import price_asof
from dart_client import DartClient, DartError
from factor.pead import standalone_from_cumulative, REPRT

YEARS = range(2020, 2026)   # bsns_year 2020~2025 (6개년 * 4분기 = 최대 24분기/종목)


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
    print(f"유니버스 {len(codes)}종목 · {list(YEARS)} 분기재무 백필(PEAD 전체수집)", flush=True)

    dart = DartClient(os.getenv("DART_API_KEY"))
    dart.corp_map()

    fin_got = date_got = 0
    for ci, code in enumerate(codes, 1):
        for y in YEARS:
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
                    print(f"\n중단 시점까지: 표준분기 {fin_got}건 저장(공시일 {date_got}건). "
                          f"내일 그대로 재실행하면 이어서 채웁니다.")
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
                    print(f"\n중단 시점까지: 표준분기 {fin_got}건 저장(공시일 {date_got}건). "
                          f"내일 그대로 재실행하면 이어서 채웁니다.")
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
