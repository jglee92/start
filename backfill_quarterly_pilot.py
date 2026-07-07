# -*- coding: utf-8 -*-
"""
PEAD 리서치 파일럿: 대형주 일부 종목의 표준분기(단독) 실적 + 정확한 공시일을 수집해
quarterly_financials에 저장한다. 파이프라인 검증용 소규모 실행 — 성공하면 전체
유니버스·기간으로 확장(backfill_quarterly.py).

사용: .\.venv\Scripts\python.exe backfill_quarterly_pilot.py
"""
from __future__ import annotations
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import db
from dart_client import DartClient, DartError
from factor.pead import standalone_from_cumulative, REPRT

YEARS = range(2020, 2026)   # bsns_year 2020~2025 (6개년 * 4분기 = 최대 24분기/종목)

# 파일럿: 시총 최상위권 대형주 위주(업종 다양성도 조금 섞음) — 파이프라인 검증 목적
PILOT_CODES = [
    "005930", "000660", "005380", "005490", "051910", "006400", "035420", "035720",
    "207940", "068270", "105560", "055550", "096770", "003670", "012330", "028260",
    "066570", "323410", "086790", "010130", "011200", "032830", "015760", "009150",
    "018260", "034730", "017670", "030200", "090430", "051900", "010950", "004020",
    "016360", "000270", "003550", "042700", "047050", "024110", "138040", "302440",
]


def main():
    conn = db.connect()
    dart = DartClient(os.getenv("DART_API_KEY"))
    dart.corp_map()

    fin_got = date_got = 0
    for ci, code in enumerate(PILOT_CODES, 1):
        for y in YEARS:
            cum = {}
            for q, reprt in REPRT.items():
                try:
                    fin = dart.get_period_financials(code, y, reprt)
                except DartError as e:
                    print(f"[중단] {code} {y}Q{q}: {e}")
                    conn.close()
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
                    return
                except Exception:
                    ddate = None
                db.save_quarterly(conn, code, y, q, s.get("revenue"),
                                  s.get("op_profit"), s.get("net_income"), ddate)
                fin_got += 1
                if ddate:
                    date_got += 1
        print(f"  ...{ci}/{len(PILOT_CODES)} {code} 완료", flush=True)

    conn.close()
    print(f"\n완료. 표준분기 {fin_got}건 저장(공시일 확보 {date_got}건).")


if __name__ == "__main__":
    main()
