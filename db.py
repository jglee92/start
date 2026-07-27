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
    # live_prices: DB 영속화 방식이 로컬 테스트 스냅샷으로 운영 데이터를 덮어쓰는
    # 사고를 유발해 폐기(순수 인메모리 캐시로 되돌림) — 구버전 DB에 남은 테이블 정리.
    conn.execute("DROP TABLE IF EXISTS live_prices")
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


def save_quarterly(conn, code: str, year: int, quarter: int, revenue, op_profit,
                   net_income, disclosed_date, debt_ratio=None, op_margin=None) -> None:
    # 컬럼명 명시 필수 — ALTER TABLE로 나중에 debt_ratio/op_margin이 추가된 구버전 DB는
    # 실제 물리적 컬럼 순서가 CREATE TABLE 선언 순서와 달라(끝에 추가됨), 위치 기반
    # VALUES(?,?,...)를 쓰면 값이 엉뚱한 컬럼에 들어간다.
    conn.execute(
        "INSERT OR REPLACE INTO quarterly_financials "
        "(code,year,quarter,revenue,op_profit,net_income,debt_ratio,op_margin,"
        "disclosed_date,fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
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


def _growth_pct(cur, prev, allow_negative=True):
    """성장률(%). DART 누적치를 단독분기로 환산(standalone_from_cumulative)하는 과정에서
    직전 공시가 정정되면 표준화된 값이 음수로 튀는 경우가 실제로 있다(매출이 음수가 되는
    등 물리적으로 불가능한 값) — 이런 깨진 기준으로 계산한 성장률은 -1000%대의 무의미한
    숫자가 되므로 노출하지 않는다. 매출(allow_negative=False)은 항상 양수여야 정상이라
    둘 중 하나라도 0 이하면 계산하지 않고, 순이익처럼 부호가 있는 값은 흑자/적자가
    전환되는 구간(분모·분자 부호가 다름)만 걸러낸다(전환 자체는 별도 이상신호로 표시)."""
    if cur is None or prev is None or prev == 0:
        return None
    if not allow_negative and (cur <= 0 or prev <= 0):
        return None
    if (cur < 0) != (prev < 0):
        return None
    pct = (cur / prev - 1) * 100
    # 기준분기가 비정상적으로 작으면(환산 잔차 등) 배율로 튀는 값이 나온다 —
    # 실제 성장이라기보다 계산 잡음일 가능성이 높아 이런 값은 숨긴다.
    if abs(pct) > 500:
        return None
    return pct


def get_recent_disclosures(conn, limit: int = 40):
    """최근 공시된 분기(disclosed_date desc, 종목당 최신 1건) + 전년 동기 대비
    매출·순이익 성장률(YoY). 전년 동기 데이터가 없으면(수집 기간이 2개년뿐이라
    초반 분기는 흔함) 직전 분기 대비(QoQ)도 같이 계산해 화면에서 대체 표시할 수
    있게 한다. 실적발표 리포트용 — '예정' 캘린더가 아니라 이미 공시된 것 중 최신순.
    같은 종목이 여러 분기로 겹쳐 들어오면 최신 것만 남긴다(중복 기업 노출 방지)."""
    all_rows = conn.execute(
        "SELECT code,year,quarter,revenue,op_profit,net_income,disclosed_date "
        "FROM quarterly_financials WHERE disclosed_date IS NOT NULL "
        "ORDER BY disclosed_date DESC, year DESC, quarter DESC").fetchall()
    seen, rows = set(), []
    for r in all_rows:
        if r[0] in seen:  # 같은 종목이 여러 분기로 겹치면(동일 disclosed_date 포함) 최신 것만
            continue
        seen.add(r[0])
        rows.append(r)
        if len(rows) >= limit:
            break
    out = []
    for code, year, quarter, revenue, op_profit, net_income, ddate in rows:
        prev_yoy = conn.execute(
            "SELECT revenue,net_income FROM quarterly_financials "
            "WHERE code=? AND year=? AND quarter=?", (code, year - 1, quarter)).fetchone()
        py, pq = (year, quarter - 1) if quarter > 1 else (year - 1, 4)
        prev_qoq = conn.execute(
            "SELECT revenue,net_income FROM quarterly_financials "
            "WHERE code=? AND year=? AND quarter=?", (code, py, pq)).fetchone()
        rev_yoy = ni_yoy = rev_qoq = ni_qoq = None
        if prev_yoy:
            rev_yoy = _growth_pct(revenue, prev_yoy[0], allow_negative=False)
            ni_yoy = _growth_pct(net_income, prev_yoy[1])
        if prev_qoq:
            rev_qoq = _growth_pct(revenue, prev_qoq[0], allow_negative=False)
            ni_qoq = _growth_pct(net_income, prev_qoq[1])
        out.append({"code": code, "year": year, "quarter": quarter, "revenue": revenue,
                    "op_profit": op_profit, "net_income": net_income,
                    "disclosed_date": ddate, "rev_yoy": rev_yoy, "ni_yoy": ni_yoy,
                    "rev_qoq": rev_qoq, "ni_qoq": ni_qoq})
    return out


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


def sane_dps(dps, price, max_yield_pct: float = 50.0):
    """DART가 간혹 '주당 현금배당금' 대신 '현금배당금총액'을 잘못 반환하는 경우가
    실제로 있었음(예: 067900 — 배당수익률이 3천만%로 계산됨). 배당수익률이 이
    상식 밖 상한(기본 50%)을 넘으면 데이터 이상치로 보고 버린다(None)."""
    if dps is None or not price:
        return dps
    if dps / price * 100 > max_yield_pct:
        return None
    return dps


def cache_history(conn, code: str, hist_df) -> None:
    """daily_prices 컬럼 구성이 DB마다 다를 수 있다 — 배포용 슬림 DB(screener_deploy.db)는
    2026-07 실제로 GitHub의 파일당 100MB 제한에 걸려 매일 push가 거부되던 걸 발견해,
    화면 어디에서도 안 쓰는(종가·거래량만 사용) open/high/low를 빼서 82MB로 줄였음
    (원본 로컬 DB는 bt_run.py가 시가를 실제로 쓰므로 그대로 유지). 그래서 이 함수는
    고정 7컬럼 INSERT 대신, 그 DB에 실제로 있는 컬럼만 골라서 넣는다 — 두 스키마
    모두에서 동작해야 하기 때문."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(daily_prices)").fetchall()}
    optional = [c for c in ("open", "high", "low") if c in cols]
    fields = ["code", "date"] + optional + ["close", "volume"]
    rows = []
    for idx, row in hist_df.iterrows():
        vals = [code, idx.strftime("%Y-%m-%d")]
        vals += [_f(row.get(c)) for c in optional]
        vals += [_f(row.get("close")), _i(row.get("volume"))]
        rows.append(tuple(vals))
    placeholders = ",".join("?" * len(fields))
    conn.executemany(
        f"INSERT OR REPLACE INTO daily_prices ({','.join(fields)}) VALUES ({placeholders})", rows)
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
