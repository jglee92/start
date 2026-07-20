# -*- coding: utf-8 -*-
"""
코스피·코스닥 전체 상장 종목(소형주 포함)의 재무/배당을 '최신 회계연도'로 갱신.
시총 필터 없이 전체를 대상으로 하되, DART 일일한도 보호를 위해 시총 큰 순으로 처리한다.

DART 사업보고서는 매년 3월말 공시되므로, 연중이면 전년도(예: 2026년 → FY2025)가 있다.
팩터 백테스트 수집은 시점정합상 과거 연도까지만 받으므로, 대시보드 최신성을 위해
여기서 최신 FY를 따로 채운다.

사용: .\.venv\Scripts\python.exe refresh_fundamentals.py
"""
from __future__ import annotations
import os
import sys
import time
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

LATEST_FY = datetime.now().year - 1   # 2026 → FY2025
QUARTER_YEARS = [datetime.now().year - 2, datetime.now().year - 1, datetime.now().year]   # 분기재무 대상 연도(YoY 비교용 1개년 추가)

# GitHub Actions 잡 하드리밋(6시간)에 걸려 스크립트가 강제종료되면 커밋 단계 전이라
# 그날 작업이 통째로 유실된다(실제로 겪은 사고). 5시간에서 스스로 깔끔히 멈춰
# 워크플로우의 git 커밋·푸시 단계가 반드시 실행되게 한다.
MAX_RUNTIME_SEC = 5 * 3600


def main():
    t0 = time.monotonic()
    conn = db.connect()
    master = build_master()
    asof = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
    elig = eligible_at(master, asof, cfg)

    # 전종목 대상(시총 필터 제거 — 소형주도 포함해 전체 코스피·코스닥 커버).
    # 시총 큰 순으로 정렬 — 시간/한도 초과로 중간에 멈춰도 중요도 높은 종목부터
    # 채워지고, 다음 실행일에 이어서 나머지가 채워짐.
    codes_marcap = []
    for r in elig.itertuples(index=False):
        if r.shares is None:
            continue
        p = price_asof(conn, r.code, asof)
        marcap = r.shares * p[0] if p else 0
        codes_marcap.append((r.code, marcap))
    codes_marcap.sort(key=lambda x: x[1], reverse=True)
    codes = [c for c, _ in codes_marcap]
    print(f"유니버스 {len(codes)}종목 · FY{LATEST_FY} 재무/배당 갱신", flush=True)

    dart = DartClient(os.getenv("DART_API_KEY"))
    dart.corp_map()
    fin_got = div_got = audit_got = q_got = 0
    stopped = None  # "quota" | "time" | None(정상완료)

    # 1단계: 재무·배당·감사의견 (종목당 최대 3콜) — 랭킹 노출에 필수인 저비용 데이터부터
    # 전 종목 커버. 분기재무(2단계)는 종목당 최대 24콜로 훨씬 비싸서, 이걸 먼저 하면
    # 앞쪽 종목만 다 받고 뒤쪽 소형주는 기본 재무조차 못 받는 상황을 방지한다.
    for i, code in enumerate(codes, 1):
        if time.monotonic() - t0 > MAX_RUNTIME_SEC:
            print(f"[시간초과] 1단계(재무/배당/감사의견) {i}/{len(codes)}에서 중단"); stopped = "time"; break
        has = conn.execute("SELECT 1 FROM financials WHERE code=? AND year=?",
                           (code, LATEST_FY)).fetchone()
        if not has:
            try:
                fin = dart.get_financials(code, year=LATEST_FY)
            except DartError as e:
                print(f"[중단] {e}"); stopped = "quota"; break
            except Exception:
                fin = None
            if fin:
                db.save_financials(conn, code, fin); fin_got += 1
        if db.get_dividend(conn, code, LATEST_FY) is None:
            try:
                dps = dart.get_dividend_dps(code, LATEST_FY)
            except Exception:
                dps = None
            db.save_dividend(conn, code, LATEST_FY, dps if dps is not None else 0.0)
            div_got += 1
        if db.get_audit_opinion(conn, code, LATEST_FY) is None:
            try:
                op = dart.get_audit_opinion(code, LATEST_FY)
            except DartError as e:
                print(f"[중단] {e}"); stopped = "quota"; break
            except Exception:
                op = None
            if op:
                db.save_audit_opinion(conn, code, LATEST_FY, op["auditor"], op["opinion"])
                audit_got += 1
        if i % 100 == 0:
            print(f"  [1단계] ...{i}/{len(codes)} (재무 {fin_got}, 배당 {div_got}, "
                  f"감사의견 {audit_got})", flush=True)

    # 2단계: 분기재무 — 1단계가 시간/한도 안에 다 끝났을 때만 진행(남은 예산 안에서).
    if stopped is None:
        for i, code in enumerate(codes, 1):
            if time.monotonic() - t0 > MAX_RUNTIME_SEC:
                print(f"[시간초과] 2단계(분기재무) {i}/{len(codes)}에서 중단"); stopped = "time"; break
            quota_exceeded = False
            for y in QUARTER_YEARS:
                have = sum(1 for q in (1, 2, 3, 4) if db.get_quarterly(conn, code, y, q))
                if have == 4:
                    continue
                cum = {}
                for q, reprt in REPRT.items():
                    try:
                        cum[q] = dart.get_period_financials(code, y, reprt)
                    except DartError as e:
                        print(f"[중단] {e}"); quota_exceeded = True; break
                    except Exception:
                        cum[q] = None
                if quota_exceeded:
                    break
                standalone = standalone_from_cumulative(cum.get(1), cum.get(2), cum.get(3), cum.get(4))
                for q in (1, 2, 3, 4):
                    s = standalone.get(q)
                    if not s or s.get("net_income") is None or db.get_quarterly(conn, code, y, q):
                        continue
                    try:
                        ddate = dart.get_report_date(code, y, REPRT[q])
                    except Exception:
                        ddate = None
                    db.save_quarterly(conn, code, y, q, s.get("revenue"), s.get("op_profit"),
                                      s.get("net_income"), ddate,
                                      debt_ratio=s.get("debt_ratio"), op_margin=s.get("op_margin"))
                    q_got += 1
            if quota_exceeded:
                stopped = "quota"; break
            if i % 100 == 0:
                print(f"  [2단계] ...{i}/{len(codes)} (분기재무 {q_got})", flush=True)
    else:
        print("[건너뜀] 1단계가 못 끝나서 2단계(분기재무)는 이번 실행에서 생략.")

    conn.close()
    print(f"완료({stopped or '정상'}). FY{LATEST_FY} 재무 {fin_got}건, 배당 {div_got}건, "
          f"감사의견 {audit_got}건, 분기재무 {q_got}건 갱신.")
    print("→ 대시보드 /api/refresh 호출 또는 서버 재시작 시 반영.")


if __name__ == "__main__":
    main()
