# -*- coding: utf-8 -*-
"""SQLite 저장. 매일 스냅샷/워치리스트를 쌓아 나중에 백테스트(2단계) 자료로 재사용."""
from __future__ import annotations
import sqlite3
import json
import os
from datetime import datetime

# 배포 시 KR_DB_PATH 로 슬림 DB 지정 가능(기본: 로컬 전체 DB)
DB_PATH = os.getenv("KR_DB_PATH") or os.path.join(
    os.path.dirname(__file__), "data", "screener.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    data_date   TEXT NOT NULL,          -- 데이터 기준일 (EOD)
    created_at  TEXT NOT NULL,          -- 실행 시각
    provider    TEXT NOT NULL,
    params_json TEXT NOT NULL
);

-- 전 종목 스냅샷 (그날 원본 보관)
CREATE TABLE IF NOT EXISTS snapshot (
    run_id       INTEGER NOT NULL,
    code         TEXT NOT NULL,
    name         TEXT,
    market       TEXT,
    open         REAL, high REAL, low REAL, close REAL,
    volume       INTEGER,
    amount       INTEGER,               -- 거래대금(원)
    marcap       INTEGER,               -- 시가총액(원)
    change_ratio REAL,                  -- 등락률(%)
    PRIMARY KEY (run_id, code)
);

-- 스크리닝 통과 워치리스트
CREATE TABLE IF NOT EXISTS watchlist (
    run_id       INTEGER NOT NULL,
    rank         INTEGER NOT NULL,
    code         TEXT NOT NULL,
    name         TEXT,
    market       TEXT,
    close        REAL,
    change_ratio REAL,                  -- 전일 등락률(%)
    high_ret     REAL,                  -- 장중 고가/시가-1 (%)
    vol_mult     REAL,                  -- 거래량 / 20일평균
    amount       INTEGER,               -- 거래대금(원)
    marcap       INTEGER,
    score        REAL,
    reasons      TEXT,                  -- 통과 사유 요약
    PRIMARY KEY (run_id, code)
);

-- 종목 일봉 캐시 (히스토리 누적 -> 백테스트 자산)
CREATE TABLE IF NOT EXISTS daily_prices (
    code   TEXT NOT NULL,
    date   TEXT NOT NULL,
    open   REAL, high REAL, low REAL, close REAL,
    volume INTEGER,
    PRIMARY KEY (code, date)
);

-- DART 배당 캐시 (주당 현금배당금 DPS, 연도별)
CREATE TABLE IF NOT EXISTS dividends (
    code TEXT NOT NULL,
    year INTEGER NOT NULL,
    dps  REAL,                          -- 주당 현금배당금(원). 0=무배당
    PRIMARY KEY (code, year)
);

-- 장중 실시간(성) 현재가 캐시(화면표시 전용, daily_prices 백테스트 데이터와 무관).
-- 디스크(DB)에 저장해서 서버 재배포/재시작으로 인메모리 캐시가 날아가도 마지막으로
-- 성공한 값이 남아있게 함 — 재배포 직후 daily_prices(하루 이상 stale 가능)까지
-- 떨어지는 것을 방지.
CREATE TABLE IF NOT EXISTS live_prices (
    code       TEXT PRIMARY KEY,
    price      REAL,
    chg_pct    REAL,
    prev_close REAL,
    updated_at TEXT
);

-- DART 감사의견 캐시 (연간, 회계감사인/감사의견)
CREATE TABLE IF NOT EXISTS audit_opinions (
    code       TEXT NOT NULL,
    year       INTEGER NOT NULL,
    auditor    TEXT,                    -- 감사인(회계법인명)
    opinion    TEXT,                    -- 감사의견(적정/한정/부적정/의견거절)
    fetched_at TEXT,
    PRIMARY KEY (code, year)
);

-- 분기별 재무(대시보드 표시용 + PEAD 리서치 겸용). revenue/op_profit/net_income은
-- '해당 분기만'의 값(11012/11014/11011의 누적치를 subtract해서 계산 — factor/pead.py 참고).
-- debt_ratio는 재무상태표 항목이라 분기 시점 스냅샷 그대로(빼기 불필요), op_margin은
-- 단독분기 기준으로 재계산됨.
CREATE TABLE IF NOT EXISTS quarterly_financials (
    code           TEXT NOT NULL,
    year           INTEGER NOT NULL,
    quarter        INTEGER NOT NULL,   -- 1~4
    revenue        REAL,
    op_profit      REAL,
    net_income     REAL,
    debt_ratio     REAL,
    op_margin      REAL,
    disclosed_date TEXT,               -- 실제 공시일(YYYY-MM-DD, list.json rcept_dt)
    fetched_at     TEXT,
    PRIMARY KEY (code, year, quarter)
);

-- DART 재무 캐시 (연간 사업보고서 주요계정)
CREATE TABLE IF NOT EXISTS financials (
    code        TEXT NOT NULL,
    year        INTEGER NOT NULL,
    fs_div      TEXT,                  -- CFS(연결)/OFS(별도)
    revenue     REAL,
    op_profit   REAL,
    net_income  REAL,
    assets      REAL,
    liabilities REAL,
    equity      REAL,
    debt_ratio  REAL,                  -- 부채총계/자본총계*100
    op_margin   REAL,                  -- 영업이익/매출액*100
    fetched_at  TEXT,
    PRIMARY KEY (code, year)
);
"""


def connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn) -> None:
    """CREATE TABLE IF NOT EXISTS는 이미 존재하는 테이블에 새 컬럼을 안 더해주므로,
    이전 배포에서 만들어진 구버전 테이블에 나중에 추가된 컬럼을 여기서 보강한다."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(quarterly_financials)").fetchall()}
    for col in ("debt_ratio", "op_margin"):
        if col not in cols:
            conn.execute(f"ALTER TABLE quarterly_financials ADD COLUMN {col} REAL")
    conn.commit()


def create_run(conn, data_date: str, provider: str, params: dict) -> int:
    cur = conn.execute(
        "INSERT INTO runs (data_date, created_at, provider, params_json) "
        "VALUES (?,?,?,?)",
        (data_date, datetime.now().isoformat(timespec="seconds"),
         provider, json.dumps(params, ensure_ascii=False)),
    )
    conn.commit()
    return cur.lastrowid


def save_snapshot(conn, run_id: int, df) -> None:
    rows = [
        (run_id, r.code, r.name, r.market,
         _f(r.open), _f(r.high), _f(r.low), _f(r.close),
         _i(r.volume), _i(r.amount), _i(r.marcap), _f(r.change_ratio))
        for r in df.itertuples(index=False)
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO snapshot VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()


def save_watchlist(conn, run_id: int, rows: list[dict]) -> None:
    data = [
        (run_id, i + 1, r["code"], r["name"], r["market"], _f(r["close"]),
         _f(r["change_ratio"]), _f(r["high_ret"]), _f(r["vol_mult"]),
         _i(r["amount"]), _i(r["marcap"]), _f(r["score"]), r["reasons"])
        for i, r in enumerate(rows)
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO watchlist VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", data)
    conn.commit()


def save_live_prices(conn, rows: dict) -> None:
    """rows = {code: {"price":, "chg_pct":, "prev_close":}}"""
    now = datetime.now().isoformat(timespec="seconds")
    data = [(c, _f(v.get("price")), _f(v.get("chg_pct")), _f(v.get("prev_close")), now)
            for c, v in rows.items()]
    conn.executemany("INSERT OR REPLACE INTO live_prices VALUES (?,?,?,?,?)", data)
    conn.commit()


def get_live_prices_cached(conn):
    """디스크에 저장된 마지막 실시간가 스냅샷 전체. {code: {price,chg_pct,prev_close,updated_at}}"""
    rows = conn.execute("SELECT code,price,chg_pct,prev_close,updated_at FROM live_prices").fetchall()
    return {r[0]: {"price": r[1], "chg_pct": r[2], "prev_close": r[3], "updated_at": r[4]}
            for r in rows}


def save_quarterly(conn, code: str, year: int, quarter: int, revenue, op_profit,
                   net_income, disclosed_date, debt_ratio=None, op_margin=None) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO quarterly_financials VALUES (?,?,?,?,?,?,?,?,?,?)",
        (code, int(year), int(quarter), _f(revenue), _f(op_profit), _f(net_income),
         _f(debt_ratio), _f(op_margin), disclosed_date,
         datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def get_quarterly(conn, code: str, year: int, quarter: int):
    r = conn.execute(
        "SELECT revenue,op_profit,net_income,debt_ratio,op_margin,disclosed_date "
        "FROM quarterly_financials WHERE code=? AND year=? AND quarter=?",
        (code, int(year), int(quarter))).fetchone()
    if not r:
        return None
    return {"revenue": r[0], "op_profit": r[1], "net_income": r[2],
            "debt_ratio": r[3], "op_margin": r[4], "disclosed_date": r[5]}


def get_quarterly_series(conn, code: str):
    """code의 모든 표준분기(연·분기 오름차순) 리스트."""
    rows = conn.execute(
        "SELECT year,quarter,revenue,op_profit,net_income,debt_ratio,op_margin,disclosed_date "
        "FROM quarterly_financials WHERE code=? ORDER BY year,quarter", (code,)).fetchall()
    return [{"year": r[0], "quarter": r[1], "revenue": r[2], "op_profit": r[3],
             "net_income": r[4], "debt_ratio": r[5], "op_margin": r[6],
             "disclosed_date": r[7]} for r in rows]


def save_financials(conn, code: str, fin: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO financials VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (code, _i(fin.get("year")), fin.get("fs_div"),
         _f(fin.get("revenue")), _f(fin.get("op_profit")),
         _f(fin.get("net_income")), _f(fin.get("assets")),
         _f(fin.get("liabilities")), _f(fin.get("equity")),
         _f(fin.get("debt_ratio")), _f(fin.get("op_margin")),
         datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def get_cached_financials(conn, code: str):
    cur = conn.execute(
        "SELECT year,fs_div,revenue,op_profit,net_income,assets,liabilities,"
        "equity,debt_ratio,op_margin FROM financials WHERE code=?", (code,))
    row = cur.fetchone()
    if not row:
        return None
    keys = ["year", "fs_div", "revenue", "op_profit", "net_income", "assets",
            "liabilities", "equity", "debt_ratio", "op_margin"]
    return dict(zip(keys, row))


def save_audit_opinion(conn, code: str, year: int, auditor, opinion) -> None:
    conn.execute("INSERT OR REPLACE INTO audit_opinions VALUES (?,?,?,?,?)",
                 (code, int(year), auditor, opinion,
                  datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def get_audit_opinion(conn, code: str, year: int = None):
    """year 지정 시 해당 연도, 없으면 캐시된 것 중 최신 연도."""
    if year is not None:
        r = conn.execute(
            "SELECT year,auditor,opinion FROM audit_opinions WHERE code=? AND year=?",
            (code, int(year))).fetchone()
    else:
        r = conn.execute(
            "SELECT year,auditor,opinion FROM audit_opinions WHERE code=? "
            "ORDER BY year DESC LIMIT 1", (code,)).fetchone()
    if not r:
        return None
    return {"year": r[0], "auditor": r[1], "opinion": r[2]}


def save_dividend(conn, code: str, year: int, dps) -> None:
    conn.execute("INSERT OR REPLACE INTO dividends VALUES (?,?,?)",
                 (code, int(year), _f(dps)))
    conn.commit()


def get_dividend(conn, code: str, year: int):
    r = conn.execute("SELECT dps FROM dividends WHERE code=? AND year=?",
                     (code, int(year))).fetchone()
    return r[0] if r else None


def cache_history(conn, code: str, hist_df) -> None:
    rows = [
        (code, idx.strftime("%Y-%m-%d"),
         _f(row.get("open")), _f(row.get("high")), _f(row.get("low")),
         _f(row.get("close")), _i(row.get("volume")))
        for idx, row in hist_df.iterrows()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO daily_prices VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()


def _f(v):
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    try:
        if v is None:
            return None
        return int(v)
    except (TypeError, ValueError):
        return None
