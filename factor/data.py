# -*- coding: utf-8 -*-
"""팩터 백테스트용 데이터 수집 (가격·시점정합 재무). 캐시·재개 가능."""
from __future__ import annotations
import os
import sys
import json
import time
import socket
from datetime import datetime

# fdr/requests 는 타임아웃 미노출 → 소켓 전역 타임아웃으로 hang 방지(예외로 전환→재시도)
socket.setdefaulttimeout(20)

import FinanceDataReader as fdr

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
FIN_MISS_PATH = os.path.join(DATA_DIR, "fin_miss.json")


# ---------- 가격 ----------
def _fetch_one(code, start, end):
    try:
        h = fdr.DataReader(code, start, end)
        if h is None or len(h) == 0:
            return None
        h = h.rename(columns=str.lower)
        keep = [x for x in ["open", "high", "low", "close", "volume"]
                if x in h.columns]
        return h[keep]
    except Exception:
        return None


def ensure_prices(conn, codes, start: str, end: str, min_rows: int = 30,
                  log_every: int = 100, workers: int = 10, per_timeout: int = 25):
    """codes 각 종목 일봉을 daily_prices 에 적재. 스레드풀+하드타임아웃(hang 방지).
    단순 row수만 보면 '최근 데이터만 있는' 종목(예: 최근 전종목 확장으로 새로 들어와
    최근 시세만 쌓인 소형주)을 이미 커버된 걸로 오판해 과거(start) 데이터를 영영
    못 채우는 문제가 실제로 있었음 — MIN(date)가 start를 못 따라잡으면 대상에 포함.
    단, start(달력일)가 휴장일이면 첫 거래일이 며칠 뒤이므로, GRACE_DAYS 만큼
    여유를 둬 '이미 완전한' 캐시를 매 실행마다 재수집하는 오판을 막는다."""
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timedelta
    GRACE_DAYS = 14   # start가 신정 연휴 등 휴장이면 첫 거래일이 뒤로 밀림
    cutoff = (datetime.fromisoformat(start) +
              timedelta(days=GRACE_DAYS)).strftime("%Y-%m-%d")
    todo = []
    for c in codes:
        n, min_date = conn.execute(
            "SELECT COUNT(*), MIN(date) FROM daily_prices WHERE code=?", (c,)).fetchone()
        if n < min_rows or min_date is None or min_date > cutoff:
            todo.append(c)
    print(f"가격 수집: 대상 {len(todo)}/{len(codes)}종목 (workers={workers})",
          flush=True)
    got = 0
    ex = ThreadPoolExecutor(max_workers=workers)
    futures = [(c, ex.submit(_fetch_one, c, start, end)) for c in todo]
    for i, (c, fut) in enumerate(futures, 1):
        try:
            df = fut.result(timeout=per_timeout)   # hang 은 여기서 끊고 skip
        except Exception:
            df = None
        if df is not None and len(df):
            db.cache_history(conn, c, df)
            got += 1
        if i % log_every == 0:
            print(f"  ...{i}/{len(todo)} (적재 {got})", flush=True)
    ex.shutdown(wait=False, cancel_futures=True)
    return got


def price_asof(conn, code: str, date: str):
    """date 이하 최근 종가 (code). (close, date) 또는 None."""
    r = conn.execute(
        "SELECT close,date FROM daily_prices WHERE code=? AND date<=? "
        "AND close IS NOT NULL ORDER BY date DESC LIMIT 1", (code, date)).fetchone()
    return (r[0], r[1]) if r else None


def price_first_after(conn, code: str, date: str):
    """date 이상 최초 종가 (매수 체결 근사)."""
    r = conn.execute(
        "SELECT close,date FROM daily_prices WHERE code=? AND date>=? "
        "AND close IS NOT NULL ORDER BY date ASC LIMIT 1", (code, date)).fetchone()
    return (r[0], r[1]) if r else None


# ---------- 시점정합 재무 ----------
def _load_miss():
    if os.path.exists(FIN_MISS_PATH):
        with open(FIN_MISS_PATH, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def _save_miss(s):
    with open(FIN_MISS_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(s), f)


def ensure_financials(dart, conn, pairs, log_every: int = 50):
    """pairs = [(code, fiscal_year), ...] 재무를 특정 연도로 정확히 수집(폴백 없음)."""
    from dart_client import DartError
    miss = _load_miss()
    todo = []
    for code, year in pairs:
        if financials_for_year(conn, code, year) is not None:
            continue
        if f"{code}:{year}" in miss:
            continue
        todo.append((code, year))
    print(f"재무 수집(시점정합): 대상 {len(todo)}쌍")
    got = 0
    for i, (code, year) in enumerate(todo, 1):
        fin = None
        for attempt in range(3):
            try:
                fin = dart.get_financials(code, year=year)  # year 고정 → 폴백X
                break
            except DartError as e:
                print(f"  [중단] {e}")
                _save_miss(miss)
                return got
            except Exception:
                time.sleep(0.4)
        if fin:
            db.save_financials(conn, code, fin)
            got += 1
        else:
            miss.add(f"{code}:{year}")
        if i % log_every == 0:
            print(f"  ...{i}/{len(todo)} (적재 {got})")
            _save_miss(miss)
    _save_miss(miss)
    return got


def ensure_dividends(dart, conn, pairs, log_every: int = 100):
    """pairs=[(code, year)] 주당 현금배당금(DPS)을 수집. 무배당은 0으로 저장."""
    from dart_client import DartError
    todo = [(c, y) for c, y in pairs if db.get_dividend(conn, c, y) is None]
    print(f"배당 수집: 대상 {len(todo)}쌍", flush=True)
    got = 0
    for i, (code, year) in enumerate(todo, 1):
        dps = None
        for attempt in range(3):
            try:
                dps = dart.get_dividend_dps(code, year)
                break
            except DartError as e:
                print(f"  [중단] {e}")
                return got
            except Exception:
                time.sleep(0.4)
        db.save_dividend(conn, code, year, dps if dps is not None else 0.0)
        got += 1
        if i % log_every == 0:
            print(f"  ...{i}/{len(todo)}", flush=True)
    return got


def financials_for_year(conn, code: str, year: int):
    """code 의 특정 회계연도 재무(있으면). financials 테이블은 code당 최신 1행이므로
    year 일치 시만 반환."""
    row = conn.execute(
        "SELECT year,revenue,op_profit,net_income,assets,liabilities,equity,"
        "debt_ratio,op_margin FROM financials WHERE code=? AND year=?",
        (code, year)).fetchone()
    if not row:
        return None
    keys = ["year", "revenue", "op_profit", "net_income", "assets",
            "liabilities", "equity", "debt_ratio", "op_margin"]
    return dict(zip(keys, row))
