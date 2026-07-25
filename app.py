# -*- coding: utf-8 -*-
"""
가치+퀄리티 팩터 대시보드 (FastAPI).

실행:  .\.venv\Scripts\python.exe -m uvicorn app:app --reload --port 8000
접속:  http://127.0.0.1:8000

데이터: screener.db (수집된 재무/가격) + factor.current 랭킹.
백테스트 요약은 factor.backtest 결과(정직본)를 임베드.
"""
from __future__ import annotations
import os
import random
import time
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

import db
from factor.universe import build_master
from factor.current import compute_ranking

app = FastAPI(title="가치+퀄리티 팩터 대시보드")


@app.on_event("startup")
def _start_proactive_refresh():
    """실시간가/지수 캐시가 '요청이 와야 갱신을 시작'하는 구조라, 트래픽이 뜸하면
    사용자가 새로고침해도 항상 한 박자 늦은(캐시 갱신 트리거만 하고 예전 값을 보여주는)
    값을 보게 되는 문제가 있었음(실사용자 피드백으로 발견). 서버 자체가 백그라운드에서
    주기적으로 미리 갱신해두면, 사용자가 실제로 볼 때는 이미 최신 상태일 확률이 높아짐."""
    import threading
    import time as _time

    def _loop():
        while True:
            try:
                get_live_prices()
                get_market_indices()
            except Exception:
                pass
            _time.sleep(30)

    threading.Thread(target=_loop, daemon=True).start()
    threading.Thread(target=_warm_heavy_caches, daemon=True).start()


def _warm_heavy_caches():
    """Render 무료티어는 15분 무접속 시 슬립되고, 다음 요청이 서버를 깨우면 모든
    인메모리 캐시가 초기화된 상태로 시작한다. 그 첫 요청을 받은 사용자가 시장동향·
    리포트 섹션 전부를 콜드로(수십 초씩) 계산하며 기다리는 문제가 실제로 있었음.
    프로세스가 뜨자마자(콜드부팅이든 배포 재시작이든) 무거운 캐시들을 백그라운드에서
    미리 계산해둬서, 실제 첫 방문자가 오기 전에 최대한 데워두는 게 목적."""
    import time as _time
    try:
        get_ranking()
    except Exception:
        pass
    try:
        get_halted_codes()   # 자체적으로 백그라운드 스레드를 또 띄우지만 최대한 빨리 트리거
    except Exception:
        pass
    try:
        from factor.themes import compute_theme_perf
        conn = _conn()
        _cache["theme_perf"] = compute_theme_perf(conn, get_tmap())
        conn.close()
    except Exception:
        pass
    try:
        from factor.themes import compute_group_hierarchy
        conn = _conn()
        if _cache["master"] is None:
            _cache["master"] = build_master()
        _cache["theme_groups"] = compute_group_hierarchy(conn, get_tmap(), master=_cache["master"])
        conn.close()
    except Exception:
        pass
    # get_halted_codes()의 전종목 스캔은 30~120초 걸릴 수 있어, 완료될 때까지
    # 잠깐 더 기다렸다가 거래정지 페이지 조립 캐시까지 같이 데워둔다(있으면 즉시 반환).
    for _ in range(24):    # 최대 2분 대기(5초 x 24)
        if not _cache.get("halted_refreshing"):
            break
        _time.sleep(5)
    try:
        _halted_stocks_data()
    except Exception:
        pass

# --- 백테스트 결과 (정직본, factor.backtest 실행값) ---
BACKTEST = {
    "설정": "KOSPI+KOSDAQ 시총≥3000억 상위200 · 가치+퀄리티 top20 동일가중 · "
             "연1회 리밸런싱 · 시점정합 · 상폐포함 · 배당포함(세후) · 왕복비용 0.41%",
    "years": [
        {"y": 2018, "strat": -9.7, "bench": -15.4, "kospi": -10.3},
        {"y": 2019, "strat": -19.6, "bench": -23.1, "kospi": -11.4},
        {"y": 2020, "strat": 75.5, "bench": 55.4, "kospi": 64.8},
        {"y": 2021, "strat": -3.3, "bench": -11.1, "kospi": -16.8},
        {"y": 2022, "strat": -7.5, "bench": -12.5, "kospi": -5.4},
        {"y": 2023, "strat": -6.7, "bench": 10.6, "kospi": 6.5},
        {"y": 2024, "strat": 1.7, "bench": 3.8, "kospi": -6.4},
    ],
    "cum": {"strat_total": 8.1, "strat_cagr": 1.1,
            "bench_total": -9.7, "bench_cagr": -1.4,
            "kospi_total": 2.7, "kospi_cagr": 0.4,
            "excess_pa": 3.2, "win": "5/7"},
    "note": "배당 포함(총수익) 시 전략 CAGR +1.1%로 유니버스(-1.4%)·코스피(+0.4%)를 모두 이김 "
            "— 상대·절대 모두 검증. 단 +1.1%는 낮음(중소형 롱온리·2023 테마랠리 부진). "
            "시장국면 필터(200일선)는 2020 반등을 놓쳐 역효과라 제외. "
            "남은 레버: 소형주 확장(가치프리미엄 강함). 매수추천 아님·리서치용.",
}

_cache = {"ranking": None, "master": None}


def _conn():
    return db.connect()


@app.get("/api/debug/halt-status")
def debug_halt_status():
    """거래정지 스캔 진행 상태 원격 확인용(운영 진단). 콜드부팅 직후 첫 스캔이
    실제로 얼마나 걸리는지, 멈춰 있는 건 아닌지 값을 안 기다리고 바로 볼 수 있다."""
    from datetime import datetime
    import live_price
    ts = _cache.get("halted_ts")
    age = None
    if ts:
        age = round((datetime.now(live_price.KST) - ts).total_seconds(), 1)
    return {
        "halted_refreshing": bool(_cache.get("halted_refreshing")),
        "halted_ts": ts.isoformat() if ts else None,
        "halted_ts_age_sec": age,
        "halted_count": len(_cache.get("halted") or []),
    }


def get_ranking():
    if _cache["ranking"] is None:
        conn = _conn()
        if _cache["master"] is None:
            _cache["master"] = build_master()
        _cache["ranking"] = compute_ranking(conn, master=_cache["master"])
        conn.close()
    halted = get_halted_codes()
    if not halted:
        return _cache["ranking"]
    return [r for r in _cache["ranking"] if r["code"] not in halted]


def get_halted_codes():
    """현재 거래정지 상태인 종목 코드 집합 — 전 종목 대상, 매수·매도 자체가 불가능한
    종목이 랭킹·섹터·비교 등 어디에도 섞여 나오지 않도록 get_ranking()에서 걸러내는 용도.
    거래정지는 분단위로 바뀌는 게 아니라서 실시간가(get_live_prices)보다 훨씬 긴 TTL로
    캐시(폴링 서버 부담도 줄임). 오래됐어도 즉시 반환하고 갱신은 백그라운드에서."""
    import threading
    from datetime import datetime
    import live_price
    from factor.universe import eligible_at
    import factor_config as fcfg
    TTL = 1800   # 30분
    ts = _cache.get("halted_ts")
    now_kst = datetime.now(live_price.KST)
    stale = ts is None or (now_kst - ts).total_seconds() > TTL
    if stale and not _cache.get("halted_refreshing"):
        _cache["halted_refreshing"] = True

        def _bg():
            try:
                if _cache["master"] is None:
                    _cache["master"] = build_master()
                asof = get_asof()
                elig = eligible_at(_cache["master"], asof, fcfg)
                codes = [r.code for r in elig.itertuples(index=False)]
                _cache["halted"] = live_price.fetch_halted_set(codes)
                _cache["halted_ts"] = datetime.now(live_price.KST)
            finally:
                _cache["halted_refreshing"] = False

        threading.Thread(target=_bg, daemon=True).start()
    return _cache.get("halted") or set()


def get_asof():
    """전체 데이터의 실제 최신 가격일. (특정 1위 종목의 마지막 거래일이 아니라
    daily_prices 전체의 MAX(date) — 개별 종목의 데이터 공백에 영향받지 않음)"""
    if _cache.get("asof") is None:
        conn = _conn()
        row = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()
        conn.close()
        _cache["asof"] = row[0] if row else None
    return _cache["asof"]


def get_ranking_asof(days_ago: int):
    """days_ago일 전 가격 기준으로 재계산한 랭킹(재무는 항상 최신). 순위 변동 비교용."""
    key = f"rk_{days_ago}d"
    if _cache.get(key) is None:
        from datetime import date, timedelta
        asof = get_asof()
        ref = (date.fromisoformat(asof) - timedelta(days=days_ago)).isoformat()
        conn = _conn()
        if _cache["master"] is None:
            _cache["master"] = build_master()
        _cache[key] = compute_ranking(conn, master=_cache["master"], ref_date=ref)
        conn.close()
    return _cache[key]


def get_live_prices():
    """현재가 캐시(화면표시 전용, daily_prices와 무관). 갱신 시도는 09:00~19:00로
    정규장(15:30 마감)보다 넓게 잡음 — 장마감~저녁 정식 daily_prices 갱신(19:00) 사이
    공백에서 daily_prices가 하루 이상 stale한 채로 노출되던 문제가 실제로 있었음.
    전체 종목 조회에 30초+ 걸려서 요청을 막으면 안 됨 -> stale-while-revalidate:
    캐시(오래됐어도)는 즉시 반환하고, 갱신은 백그라운드 스레드에서.
    순수 인메모리 캐시(재배포 시 초기화됨) — DB(git 커밋으로 배포되는 파일)에 저장하면
    로컬 테스트 스냅샷이 실수로 운영서버의 최신 실시간가를 덮어써버리는 사고가 날 수 있어
    (실제로 한 번 발생) 의도적으로 영속화하지 않음."""
    import threading
    import live_price
    from datetime import datetime
    if not live_price.should_refresh_live():
        return _cache.get("live_prices") or {}
    ts = _cache.get("live_prices_ts")
    now_kst = datetime.now(live_price.KST)
    stale = ts is None or (now_kst - ts).total_seconds() > live_price.TTL_SECONDS
    if stale and not _cache.get("live_prices_refreshing"):
        _cache["live_prices_refreshing"] = True

        def _bg():
            try:
                codes = [r["code"] for r in get_ranking()]
                fresh = live_price.fetch_many(codes)
                if fresh:
                    _cache["live_prices"] = {**(_cache.get("live_prices") or {}), **fresh}
                    _cache["live_prices_ts"] = datetime.now(live_price.KST)
            finally:
                _cache["live_prices_refreshing"] = False

        threading.Thread(target=_bg, daemon=True).start()
    return _cache.get("live_prices") or {}


def get_live_updated_at():
    """장중 실시간가가 마지막으로 성공 갱신된 시각(HH:MM, KST) — 화면에 '5분마다 갱신' 같은
    부정확한 문구 대신 실제 시각을 보여주기 위함."""
    ts = _cache.get("live_prices_ts")
    return ts.strftime("%H:%M") if ts else None


def get_market_indices():
    """코스피/코스닥/나스닥/S&P500/국제 금 - 홈 화면 표시 전용. get_live_prices()와
    동일하게 stale-while-revalidate + 순수 인메모리 캐시(DB에 저장 안 함)."""
    import threading
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    TTL_SECONDS = 60
    ts = _cache.get("indices_ts")
    now_kst = datetime.now(KST)
    stale = ts is None or (now_kst - ts).total_seconds() > TTL_SECONDS
    if stale and not _cache.get("indices_refreshing"):
        _cache["indices_refreshing"] = True

        def _bg():
            try:
                import market_indices
                fresh = market_indices.fetch_indices()
                if fresh:
                    _cache["indices"] = fresh
                    _cache["indices_ts"] = datetime.now(KST)
            finally:
                _cache["indices_refreshing"] = False

        threading.Thread(target=_bg, daemon=True).start()
    return _cache.get("indices") or {}


@app.get("/api/indices")
def api_indices():
    return {"indices": get_market_indices()}


@app.get("/api/indices/{key}/history")
def api_indices_history(key: str, range: str = "6mo"):
    import market_indices
    if range not in ("1mo", "6mo", "1y"):
        range = "6mo"
    cache_key = f"idx_hist_{key}_{range}"
    cached = _cache.get(cache_key)
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    if cached and (now_kst - cached["ts"]).total_seconds() < 900:
        return cached["data"]
    data = market_indices.fetch_history(key, range)
    if not data:
        raise HTTPException(404, "지수 없음")
    _cache[cache_key] = {"data": data, "ts": now_kst}
    return data


def _rank_movers(rk_now, rk_past, top_n=8):
    """현재 랭킹과 과거(가격만 되돌린) 랭킹을 비교한 순위 상승/하락 상위 top_n.
    재무는 최신 그대로 쓰므로 순수 가격 변동에 의한 밸류에이션 변화가 원인."""
    past_rank = {r["code"]: r["rank"] for r in rk_past}
    past_score = {r["code"]: r["score"] for r in rk_past}
    diffs = []
    for r in rk_now:
        pr = past_rank.get(r["code"])
        if pr is None:
            continue
        diffs.append({
            "code": r["code"], "name": r["name"], "rank": r["rank"], "prev_rank": pr,
            "rank_change": pr - r["rank"], "score": r["score"],
            "score_change": round(r["score"] - past_score[r["code"]], 1),
        })
    up = sorted([d for d in diffs if d["rank_change"] > 0],
                key=lambda d: d["rank_change"], reverse=True)[:top_n]
    down = sorted([d for d in diffs if d["rank_change"] < 0],
                  key=lambda d: d["rank_change"])[:top_n]
    return up, down


@app.get("/api/ranking")
def api_ranking():
    rk = get_ranking()
    asof = get_asof()
    live = get_live_prices()
    slim = []
    for r in rk:
        lp = live.get(r["code"])
        price = lp["price"] if lp else r.get("price")
        chg_pct = lp["chg_pct"] if lp else r.get("chg_pct")
        # 라이브가 있으면 전일종가도 같은 소스(네이버)에서 뽑아 price와 시점을 맞춘다.
        # daily_prices 기준 prev_close와 섞으면 하루치 시차로 어긋나 보일 수 있음.
        prev_close = (lp.get("prev_close") if lp else None) or r.get("prev_close")
        slim.append({
            "rank": r["rank"], "code": r["code"], "name": r["name"],
            "market": r["market"], "sector": r.get("sector"), "score": r["score"],
            "per": _r(r["per"]), "pbr": _r(r["pbr"], 2), "psr": _r(r["psr"], 2),
            "roe": _r(r["roe"]), "op_margin": _r(r["op_margin"]),
            "debt_ratio": _r(r["debt_ratio"], 0),
            "marcap_eok": round(r["marcap"] / 1e8),
            "small_cap": r.get("small_cap", False),
            "fiscal_year": r["fiscal_year"],
            "price": price, "chg_pct": _r(chg_pct, 2), "live": bool(lp),
            "prev_close": prev_close,
            "revenue_eok": round(r["revenue"] / 1e8) if r.get("revenue") else None,
            "op_profit_eok": round(r["op_profit"] / 1e8) if r.get("op_profit") else None,
            "div_yield": _r(r.get("div_yield"), 2),
            "rev_growth": _r(r.get("rev_growth")),
            "dims": r.get("dims"), "flags": r.get("flags") or [],
        })
    return {"asof": asof, "count": len(slim), "rows": slim,
            "live_updated_at": get_live_updated_at()}


def _period_returns(conn, code):
    """WoW/MoM/QoQ/YoY 가격 변동률(%). 달력일 기준 '그 날짜 이하 최근 종가'로 비교."""
    from datetime import datetime, timedelta
    latest = conn.execute(
        "SELECT close,date FROM daily_prices WHERE code=? AND close IS NOT NULL "
        "ORDER BY date DESC LIMIT 1", (code,)).fetchone()
    if not latest:
        return {}
    close, date = latest
    d0 = datetime.strptime(date, "%Y-%m-%d")
    out = {}
    for key, days in (("wow", 7), ("mom", 30), ("qoq", 91), ("yoy", 365)):
        target = (d0 - timedelta(days=days)).strftime("%Y-%m-%d")
        r = conn.execute(
            "SELECT close FROM daily_prices WHERE code=? AND close IS NOT NULL "
            "AND date<=? ORDER BY date DESC LIMIT 1", (code, target)).fetchone()
        out[key] = round((close / r[0] - 1) * 100, 1) if r and r[0] else None
    return out


@app.get("/api/stock/{code}")
def api_stock(code: str):
    rk = get_ranking()
    row = next((r for r in rk if r["code"] == code), None)
    conn = _conn()
    fins = conn.execute(
        "SELECT year,revenue,op_profit,net_income,equity,liabilities,"
        "debt_ratio,op_margin FROM financials WHERE code=? ORDER BY year", (code,)
    ).fetchall()
    prices = conn.execute(
        "SELECT date,close FROM daily_prices WHERE code=? AND close IS NOT NULL "
        "AND date>=? ORDER BY date", (code, "2023-01-01")).fetchall()
    period_returns = _period_returns(conn, code)
    audit = db.get_audit_opinion(conn, code)
    quarterly = db.get_quarterly_series(conn, code)
    conn.close()
    if row is None and not fins:
        raise HTTPException(404, "종목 없음")
    name = row["name"] if row else _name_of(code)
    themes = _stock_theme_pairs(code)
    live = get_live_prices().get(code)
    return {
        "code": code, "name": name, "themes": themes, "period_returns": period_returns,
        "audit": audit, "quarterly": quarterly,
        "summary": None if row is None else {
            "rank": row["rank"], "score": row["score"], "market": row["market"],
            "price": live["price"] if live else row["price"],
            "chg_pct": _r(live["chg_pct"] if live else row.get("chg_pct"), 2),
            "live": bool(live),
            "prev_close": (live.get("prev_close") if live else None) or row.get("prev_close"),
            "marcap_eok": round(row["marcap"] / 1e8),
            "per": _r(row["per"]), "pbr": _r(row["pbr"], 2),
            "psr": _r(row["psr"], 2), "roe": _r(row["roe"]),
            "op_margin": _r(row["op_margin"]), "debt_ratio": _r(row["debt_ratio"], 0),
            "div_yield": _r(row.get("div_yield"), 2), "rev_growth": _r(row.get("rev_growth")),
            "breakdown": row["breakdown"], "dims": row.get("dims"),
            "flags": row.get("flags") or [],
            "small_cap": row.get("small_cap", False),
        },
        "financials": [{
            "year": f[0], "revenue": f[1], "op_profit": f[2], "net_income": f[3],
            "equity": f[4], "liabilities": f[5], "debt_ratio": _r(f[6], 0),
            "op_margin": _r(f[7]),
        } for f in fins],
        "prices": [{"date": p[0], "close": p[1]} for p in prices[::2]],  # 2일 간격 샘플
    }


@app.get("/api/backtest")
def api_backtest():
    return JSONResponse(BACKTEST)


def get_tmap():
    if _cache.get("tmap") is None:
        from factor.themes import load_theme_map
        _cache["tmap"] = load_theme_map()
    return _cache["tmap"]


@app.get("/api/themes")
def api_themes():
    """네이버 테마별 최근 1M/3M 동일가중 수익률 (요즘 강세 테마)."""
    if _cache.get("theme_perf") is None:
        from factor.themes import compute_theme_perf
        conn = _conn()
        _cache["theme_perf"] = compute_theme_perf(conn, get_tmap())
        conn.close()
    # 클러터·편차 축소: 구성종목 충분(전체 8+, 계산에 3+ 사용)한 테마만
    rows = [r for r in _cache["theme_perf"]
            if r.get("used", 0) >= 3 and r["count"] >= 8]
    rows.sort(key=lambda r: (r["ret_1m"] is not None, r["ret_1m"]), reverse=True)
    return {"count": len(rows), "rows": rows}


@app.get("/api/theme-groups")
def api_theme_groups():
    """대그룹→중그룹→소그룹(테마) 3단계 + 최근 수익률."""
    if _cache.get("theme_groups") is None:
        from factor.themes import compute_group_hierarchy
        conn = _conn()
        if _cache["master"] is None:
            _cache["master"] = build_master()
        _cache["theme_groups"] = compute_group_hierarchy(
            conn, get_tmap(), master=_cache["master"])
        conn.close()
    return {"groups": _cache["theme_groups"]}


@app.get("/api/theme/{ident}")
def api_theme(ident: str):
    """테마 구성종목(현재 랭킹 데이터 결합) + 상위 종목 뉴스 통합.
    ident 는 테마번호(no) 우선, 못 찾으면 이름으로 폴백. 테마명에 '/' 등 특수문자가
    있으면 URL 경로 매칭이 깨지므로 번호(no) 사용을 권장(프론트도 no로 호출)."""
    tmap = get_tmap()
    theme = tmap["themes"].get(ident)
    if not theme:
        theme = next((t for t in tmap["themes"].values() if t["name"] == ident), None)
    if not theme:
        raise HTTPException(404, "테마 없음")
    name = theme["name"]
    rk = {r["code"]: r for r in get_ranking()}
    stocks = []
    for c in theme["codes"]:
        r = rk.get(c)
        if r:
            stocks.append({"code": c, "name": r["name"], "in_rank": True,
                           "score": r["score"], "per": _r(r["per"]),
                           "pbr": _r(r["pbr"], 2), "roe": _r(r["roe"]),
                           "marcap_eok": round(r["marcap"] / 1e8),
                           "sector": r.get("sector"),
                           "small_cap": r.get("small_cap", False)})
        else:
            stocks.append({"code": c, "name": _name_of(c), "in_rank": False})
    stocks.sort(key=lambda s: (s["in_rank"], s.get("score", 0)), reverse=True)
    news = _merged_news(stocks[:3])
    return {"theme": name, "count": len(stocks), "stocks": stocks, "news": news}


def _merged_news(stocks, per_stock=5, limit=12):
    """상위 종목들의 뉴스를 통합·중복제거·최신순 정렬(테마/업종/섹터 뉴스 공용)."""
    merged = []
    for s in stocks:
        for it in _google_news(f"{s['name']} 주식", keep_ts=True, stock_name=s['name'])[:per_stock]:
            it["stock"] = s["name"]
            merged.append(it)
    seen, news = set(), []
    for it in sorted(merged, key=lambda x: x.get("_ts", 0), reverse=True):
        if it["title"] in seen:
            continue
        seen.add(it["title"])
        news.append({k: v for k, v in it.items() if k != "_ts"})
    return news[:limit]


def _stock_theme_pairs(code):
    """code가 속한 테마의 [{no,name}] 목록. no로 안전하게 링크(이름에 '/' 등 특수문자 가능)."""
    tmap = get_tmap()
    return [{"no": no, "name": t["name"]} for no, t in tmap["themes"].items()
            if code in t["codes"]]


def _name_of(code):
    m = _cache.get("master")
    if m is None:
        m = _cache["master"] = build_master()
    hit = m[m["code"] == code]
    return hit.iloc[0]["name"] if len(hit) else code


# 전종목 확장(2026-07) 이후 /s/{code}가 434개→1,400여개로 늘면서 sitemap의 종목상세
# 비중이 92.6%까지 치솟음(애드센스가 반려했던 시점의 얇은 콘텐츠 비중보다 오히려 나쁨).
# 재무 연혁이 1개년뿐인 신규 소형주(1,242개 중 다수)는 실질적으로 얇은 페이지라, 테마
# 페이지(/t/{no})에 했던 것과 같은 패턴(noindex,follow + sitemap 제외, 사용자 열람은
# 그대로)을 적용한다. 3개년 이상 재무 연혁 = 진짜 트렌드를 보여줄 만한 종목으로 간주.
MIN_FIN_YEARS_FOR_INDEX = 3


def _stock_index_worthy(fin_year_count):
    return fin_year_count >= MIN_FIN_YEARS_FOR_INDEX


@app.get("/api/sectors")
def api_sectors():
    """섹터 로테이션(연도별 섹터 수익률) + 현재 유니버스 섹터 요약."""
    if _cache.get("sectors") is None:
        precomp = os.path.join(os.path.dirname(__file__), "data",
                               "sector_rotation.json")
        if os.path.exists(precomp):          # 배포: 미리 계산된 결과 사용
            import json as _json
            with open(precomp, encoding="utf-8") as f:
                _cache["sectors"] = _json.load(f)
        else:
            from factor.sector_rotation import compute_rotation
            conn = _conn()
            if _cache["master"] is None:
                _cache["master"] = build_master()
            _cache["sectors"] = compute_rotation(conn, master=_cache["master"])
            conn.close()
    rot = _cache["sectors"]
    # 현재 유니버스 섹터별 종목수·평균점수
    rk = get_ranking()
    agg = {}
    for r in rk:
        s = r.get("sector") or "기타"
        agg.setdefault(s, []).append(r["score"])
    current = sorted(
        [{"sector": s, "count": len(v), "avg_score": round(sum(v) / len(v), 1)}
         for s, v in agg.items()],
        key=lambda x: x["avg_score"], reverse=True)
    return {"rotation": rot, "current": current}


@app.post("/api/refresh")
def api_refresh():
    """update_data.py 실행 후 호출하면 랭킹 캐시 재계산(서버 재시작 불필요)."""
    _cache["ranking"] = None
    _cache["master"] = None
    _cache["sectors"] = None
    _cache["theme_perf"] = None
    _cache["theme_groups"] = None
    _cache["asof"] = None
    _cache["halted_page"] = None   # 거래정지 페이지 조립 캐시도 무효화(데이터 갱신 반영)
    _cache["halted_page_ts"] = None
    for k in [k for k in _cache if k.startswith("rk_")]:
        _cache[k] = None
    rk = get_ranking()
    return {"ok": True, "count": len(rk), "asof": get_asof()}


_news_cache = {}   # query -> (ts, items)

# 저품질/무관 소스 차단(블로그·커뮤니티성 집계 사이트). 필요시 추가.
_SOURCE_BLOCKLIST = {"주달", "가치투자연구소", "텐인텐", "네이버포스트", "네이버블로그",
                     "다음블로그", "티스토리", "브런치"}
_SOURCE_BLOCK_KEYWORDS = ("블로그", "카페", "커뮤니티")


def _is_blocked_source(src: str) -> bool:
    if not src:
        return False
    s = src.strip()
    if s in _SOURCE_BLOCKLIST:
        return True
    return any(k in s for k in _SOURCE_BLOCK_KEYWORDS)


def _norm(s: str) -> str:
    return "".join((s or "").split()).lower()


def _google_news(query: str, keep_ts: bool = False, stock_name: str | None = None):
    """구글뉴스 RSS(키 불필요). 30분 캐시. 최근순 정렬 + 저품질소스 차단.
    stock_name 지정 시 제목에 그 기업명이 없는 기사는 제외(무관 기사 방지)."""
    now = time.time()
    hit = _news_cache.get(query)
    if hit and now - hit[0] < 1800:
        items = hit[1]
    else:
        items = []
        try:
            q = urllib.parse.quote(query)
            url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
            r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(r.content)
            for it in root.findall(".//item"):
                title = it.findtext("title") or ""
                src = it.find("{*}source")
                srcname = src.text if src is not None else ""
                if srcname and title.endswith(" - " + srcname):
                    title = title[: -(len(srcname) + 3)]
                if _is_blocked_source(srcname):
                    continue
                raw = it.findtext("pubDate") or ""
                try:
                    ts = parsedate_to_datetime(raw).timestamp()
                except Exception:
                    ts = 0
                items.append({"title": title, "link": it.findtext("link"),
                              "pub": raw[:16], "_ts": ts, "source": srcname})
            items.sort(key=lambda x: x["_ts"], reverse=True)
            seen, dedup = set(), []          # 중복 제목 제거
            for it in items:
                key = _norm(it["title"])[:40]
                if key in seen:
                    continue
                seen.add(key)
                dedup.append(it)
            items = dedup
        except Exception:
            items = []
        _news_cache[query] = (now, items)
    if stock_name:
        core = _norm(stock_name)
        items = [x for x in items if core and core in _norm(x["title"])]
    if keep_ts:
        return [dict(x) for x in items]
    return [{k: v for k, v in x.items() if k != "_ts"} for x in items]


_disc_cache = {}   # code -> (ts, items)
_dart_singleton = {}


def _get_dart():
    if "c" not in _dart_singleton:
        from dart_client import DartClient
        d = DartClient(os.getenv("DART_API_KEY", ""))
        d.corp_map()
        _dart_singleton["c"] = d
    return _dart_singleton["c"]


@app.get("/api/disclosures/{code}")
def api_disclosures(code: str):
    """DART 공식 공시목록 API(크롤링 아님). 6시간 캐시."""
    now = time.time()
    hit = _disc_cache.get(code)
    if hit and now - hit[0] < 21600:
        return hit[1]
    try:
        d = _get_dart()
        items = d.get_disclosures(code, count=8)
        out = {"code": code, "items": items}
    except Exception as e:
        out = {"code": code, "items": [], "error": str(e)}
    _disc_cache[code] = (now, out)
    return out


@app.get("/api/news/{code}")
def api_news(code: str):
    rk = get_ranking()
    row = next((r for r in rk if r["code"] == code), None)
    name = row["name"] if row else _name_of(code)
    return {"code": code, "name": name,
            "items": _google_news(f"{name} 주식", stock_name=name)[:10]}


@app.get("/api/sector/{name}")
def api_sector(name: str):
    """섹터의 구성 종목(현재 랭킹) + 상위 종목 뉴스 통합(최근순)."""
    rk = get_ranking()
    stocks = [{
        "rank": r["rank"], "code": r["code"], "name": r["name"],
        "score": r["score"], "per": _r(r["per"]), "pbr": _r(r["pbr"], 2),
        "roe": _r(r["roe"]), "marcap_eok": round(r["marcap"] / 1e8),
    } for r in rk if (r.get("sector") or "기타") == name]
    # 상위 3종목 뉴스 병합
    merged = []
    for s in stocks[:3]:
        for it in _google_news(f"{s['name']} 주식", keep_ts=True, stock_name=s['name'])[:5]:
            it["stock"] = s["name"]
            merged.append(it)
    seen, news = set(), []
    for it in sorted(merged, key=lambda x: x.get("_ts", 0), reverse=True):
        if it["title"] in seen:
            continue
        seen.add(it["title"])
        news.append({k: v for k, v in it.items() if k != "_ts"})
    return {"sector": name, "count": len(stocks), "stocks": stocks, "news": news[:12]}


# 배포 시 실제 도메인으로: 예) SITE_BASE_URL=https://mydomain.com
_SITE_BASE_URL_ENV = os.getenv("SITE_BASE_URL")
BASE_URL = (_SITE_BASE_URL_ENV or "https://example.com").rstrip("/")
_STATIC = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

# 구 도메인(onrender.com)/www -> 대표 도메인 301 리다이렉트. SITE_BASE_URL이 실제로
# 설정되기 전에는(로컬 개발 등) _LEGACY_HOSTS가 비어 있어 아무 동작도 하지 않는다 —
# 환경변수 반영 전에 배포되어도 예전 도메인이 example.com으로 잘못 리다이렉트되는 사고 방지.
_CANONICAL_HOST = urllib.parse.urlsplit(BASE_URL).netloc
_LEGACY_HOSTS = {"kr-screener.onrender.com", f"www.{_CANONICAL_HOST}"} if _SITE_BASE_URL_ENV else set()


@app.middleware("http")
async def _redirect_legacy_host(request, call_next):
    host = request.headers.get("host", "").split(":")[0]
    if host in _LEGACY_HOSTS:
        target = f"{BASE_URL}{request.url.path}"
        if request.url.query:
            target += f"?{request.url.query}"
        return RedirectResponse(target, status_code=301)
    return await call_next(request)


def _page(fname):
    with open(os.path.join(_STATIC, fname), encoding="utf-8") as f:
        return f.read()


def _home_ssr_html():
    """홈 `/`에 서버렌더로 심는 콘텐츠 블록 — 통계·차트·하이라이트 카드가 전부 JS 렌더라
    크롤러는 홈에서 사실상 히어로 문단만 봤다. 여기에 건강점수 상위 종목(내부링크 /s/),
    최신 브리핑(/insights), 주요 용어(/learn) 링크를 실제 텍스트로 심어 홈의 크롤 가능한
    본문과 내부 링크를 확실히 확보한다. JS 사용자는 로드 후 이 블록의 링크가 SPA 드로어/뷰로
    열리게 재배선된다(wireHomeSsr)."""
    from content import _esc as _esc_app
    try:
        rk = get_ranking()[:10]
    except Exception:
        rk = []

    def cell(v, nd=1):
        x = _r(v, nd)
        return "–" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))

    rows = "".join(
        f'<tr><td style="text-align:left"><a href="/s/{r["code"]}">{_esc_app(r["name"])}</a>'
        f' <span class="mut" style="font-size:11px">{r["code"]}</span></td>'
        f'<td><b style="color:var(--accent)">{cell(r.get("score"))}</b></td>'
        f'<td>{cell(r.get("per"))}</td><td>{cell(r.get("pbr"), 2)}</td>'
        f'<td>{cell(r.get("roe"))}</td></tr>'
        for r in rk)
    top_table = (
        '<div class="wrap" style="overflow-x:auto"><table>'
        '<thead><tr><th style="text-align:left">종목</th><th>건강점수</th>'
        '<th>PER</th><th>PBR</th><th>ROE%</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>') if rk else ""

    briefs = _insight_dates()[:5]
    brief_items = []
    for d in briefs:
        parsed = _read_insight(d)
        label = _esc_app(parsed[0]) if parsed else f"{d} 국내증시 브리핑"
        brief_items.append(f'<li><a href="/insights/{d}">{label}</a></li>')
    brief_html = f'<ul>{"".join(brief_items)}</ul>' if brief_items else ""

    from glossary import TERMS
    key_terms = [("health-score", "건강점수"), ("anomaly-signal", "이상신호"),
                 ("audit-opinion", "감사의견"), ("per", "PER"), ("pbr", "PBR"),
                 ("roe", "ROE"), ("debt-ratio", "부채비율"), ("dividend-yield", "배당수익률"),
                 ("income-statement", "손익계산서"), ("balance-sheet", "재무상태표")]
    term_html = " · ".join(f'<a href="/learn/{s}">{lbl}</a>'
                           for s, lbl in key_terms if s in TERMS)

    return f'''<section class="home-ssr" style="margin-top:26px">
  <h2>건강점수 상위 종목</h2>
  <p class="mut" style="font-size:13px">가치(저평가)와 퀄리티(수익성·안정성)를 합친 종합 건강점수 상위 종목입니다
    (코스피·코스닥 전 종목 유니버스 · 최근 연간 재무제표 기준 · 매매 추천 아님). 종목명을 누르면
    재무제표·회계감사의견·이상신호까지 한 페이지에서 볼 수 있습니다.</p>
  {top_table}
  <h2 style="margin-top:24px">최신 데일리 브리핑</h2>
  <p class="mut" style="font-size:13px">매일 아침 코스피·코스닥의 급등락·실적발표·재무 이상신호·주도테마를 정리한 브리핑입니다.</p>
  {brief_html}
  <h2 style="margin-top:24px">자주 찾는 투자 용어</h2>
  <p>{term_html}</p>
</section>'''


@app.get("/", response_class=HTMLResponse)
def index():
    return _page("index.html").replace("<!--SSR-HOME-->", _home_ssr_html())


@app.get("/about", response_class=HTMLResponse)
def about():
    return _page("about.html")


def _theme_stocks(theme):
    rk = {r["code"]: r for r in get_ranking()}
    stocks = []
    for c in theme["codes"]:
        r = rk.get(c)
        if r:
            stocks.append({"code": c, "name": r["name"], "in_rank": True,
                           "score": r["score"], "per": _r(r["per"]),
                           "pbr": _r(r["pbr"], 2), "roe": _r(r["roe"]),
                           "sector": r.get("sector"),
                           "small_cap": r.get("small_cap", False)})
        else:
            stocks.append({"code": c, "name": _name_of(c), "in_rank": False})
    stocks.sort(key=lambda s: (s["in_rank"], s.get("score") or 0), reverse=True)
    return stocks


def _theme_perf_map():
    if _cache.get("theme_perf") is None:
        from factor.themes import compute_theme_perf
        conn = _conn()
        _cache["theme_perf"] = compute_theme_perf(conn, get_tmap())
        conn.close()
    return {t["no"]: t for t in _cache["theme_perf"]}


@app.get("/t/{no}", response_class=HTMLResponse)
def theme_page(no: str):
    from content import render_theme_page
    theme = get_tmap().get("themes", {}).get(no)
    if not theme:
        raise HTTPException(404, "테마 없음")
    stocks = _theme_stocks(theme)
    perf = _theme_perf_map().get(no)
    return render_theme_page(theme["name"], stocks, perf, f"{BASE_URL}/t/{no}")


@app.get("/api/theme-page/{no}")
def api_theme_page(no: str):
    """/t/{no} 와 동일한 풍부한 서사형 렌더링을 SPA 드로어에 그대로 재사용(중복 구현 방지)."""
    from content import render_theme_page
    theme = get_tmap().get("themes", {}).get(no)
    if not theme:
        raise HTTPException(404, "테마 없음")
    stocks = _theme_stocks(theme)
    perf = _theme_perf_map().get(no)
    html = render_theme_page(theme["name"], stocks, perf, f"{BASE_URL}/t/{no}")
    news = _merged_news(stocks[:3])
    return {"html": _extract_body(html), "name": theme["name"], "news": news}


@app.get("/s/{code}", response_class=HTMLResponse)
def stock_page(code: str):
    from content import render_stock_page
    rk = get_ranking()
    row = next((r for r in rk if r["code"] == code), None)
    conn = _conn()
    fins = conn.execute(
        "SELECT year,revenue,op_profit,net_income,equity,liabilities,"
        "debt_ratio,op_margin FROM financials WHERE code=? ORDER BY year", (code,)
    ).fetchall()
    prices = conn.execute(
        "SELECT date,close FROM daily_prices WHERE code=? AND close IS NOT NULL "
        "AND date>=? ORDER BY date", (code, "2024-04-01")).fetchall()
    period_returns = _period_returns(conn, code)
    audit = db.get_audit_opinion(conn, code)
    quarterly = db.get_quarterly_series(conn, code)
    conn.close()
    name = row["name"] if row else _name_of(code)
    if row is None and not fins:
        raise HTTPException(404, "종목 없음")
    summary = None if row is None else {
        "score": row["score"], "per": _r(row["per"]), "pbr": _r(row["pbr"], 2),
        "psr": _r(row["psr"], 2), "roe": _r(row["roe"]), "op_margin": _r(row["op_margin"]),
        "debt_ratio": _r(row["debt_ratio"], 0), "div_yield": _r(row.get("div_yield"), 2),
        "marcap_eok": round(row["marcap"] / 1e8),
        "dims": row.get("dims"), "flags": row.get("flags") or [],
        "small_cap": row.get("small_cap", False)}
    financials = [{"year": f[0], "revenue": f[1], "op_profit": f[2],
                   "net_income": f[3], "equity": f[4], "debt_ratio": _r(f[6], 0),
                   "op_margin": _r(f[7])} for f in fins]
    prices_l = [{"date": p[0], "close": p[1]} for p in prices[::2]]
    themes = _stock_theme_pairs(code)
    news = _google_news(f"{name} 주식", stock_name=name)[:10]
    disclosures = api_disclosures(code).get("items", [])
    return render_stock_page(code, name, summary, financials, prices_l, news,
                             themes, disclosures, period_returns, f"{BASE_URL}/s/{code}",
                             audit, quarterly, noindex=not _stock_index_worthy(len(fins)))


def _weekly_ctx():
    from content import render_weekly
    perf = [t for t in _theme_perf_map().values() if t["priced"] >= 5
            and t["ret_1m"] is not None]
    perf.sort(key=lambda t: t["ret_1m"], reverse=True)
    strong, weak = perf[:10], perf[-5:][::-1]
    rk = get_ranking()
    asof = get_asof()
    movers_up, movers_down = _rank_movers(rk, get_ranking_asof(7))
    return render_weekly, strong, weak, asof, movers_up, movers_down


@app.get("/weekly", response_class=HTMLResponse)
def weekly():
    render_weekly, strong, weak, asof, movers_up, movers_down = _weekly_ctx()
    return render_weekly(strong, weak, asof, f"{BASE_URL}/weekly", movers_up, movers_down)


@app.get("/api/weekly")
def api_weekly():
    render_weekly, strong, weak, asof, movers_up, movers_down = _weekly_ctx()
    html = render_weekly(strong, weak, asof, f"{BASE_URL}/weekly", movers_up, movers_down)
    return {"html": _extract_body(html)}


@app.get("/api/weekly-movers")
def api_weekly_movers():
    """SPA 주간 패널(테마 세그먼트 토글 유지용)에 순위변동만 slim JSON으로 제공."""
    rk = get_ranking()
    movers_up, movers_down = _rank_movers(rk, get_ranking_asof(7))
    return {"up": movers_up, "down": movers_down, "asof": get_asof()}


@app.get("/learn", response_class=HTMLResponse)
def learn_index():
    from glossary import render_learn_index
    return render_learn_index(f"{BASE_URL}/learn")


@app.get("/learn/{slug}", response_class=HTMLResponse)
def learn_page(slug: str):
    from glossary import TERMS, render_glossary
    if slug not in TERMS:
        raise HTTPException(404, "문서 없음")
    compare = _learn_compare(TERMS[slug])
    return render_glossary(slug, compare, f"{BASE_URL}/learn/{slug}")


@app.get("/sector-report", response_class=HTMLResponse)
def sector_report_index():
    from sector_report import render_sector_index
    return render_sector_index(get_ranking(), f"{BASE_URL}/sector-report")


@app.get("/sector-report/{slug}", response_class=HTMLResponse)
def sector_report_detail(slug: str):
    from sector_report import (compute_market_avg, compute_sector_stats,
                               render_sector_report, SLUG_TO_SECTOR)
    sector_name = SLUG_TO_SECTOR.get(slug)
    if not sector_name:
        raise HTTPException(404, "업종 없음")
    rk = get_ranking()
    stats = compute_sector_stats(rk, sector_name)
    market_avg = compute_market_avg(rk)
    return render_sector_report(sector_name, stats, market_avg,
                                f"{BASE_URL}/sector-report/{slug}")


@app.get("/api/sector-report")
def api_sector_report_index():
    from sector_report import render_sector_index
    return {"html": _extract_body(render_sector_index(get_ranking(), f"{BASE_URL}/sector-report"))}


@app.get("/api/sector-report/{slug}")
def api_sector_report_detail(slug: str):
    from sector_report import (compute_market_avg, compute_sector_stats,
                               render_sector_report, SLUG_TO_SECTOR)
    sector_name = SLUG_TO_SECTOR.get(slug)
    if not sector_name:
        raise HTTPException(404, "업종 없음")
    rk = get_ranking()
    stats = compute_sector_stats(rk, sector_name)
    market_avg = compute_market_avg(rk)
    html = render_sector_report(sector_name, stats, market_avg,
                                f"{BASE_URL}/sector-report/{slug}")
    return {"html": _extract_body(html)}


@app.get("/anomaly-report", response_class=HTMLResponse)
def anomaly_report():
    from content import render_anomaly_report
    rk = get_ranking()
    asof = get_asof()
    grouped: dict[str, list] = {}
    for r in rk:
        for f in (r.get("flags") or []):
            grouped.setdefault(f["label"], []).append({
                "code": r["code"], "name": r["name"], "marcap_eok": r.get("marcap_eok"),
                "text": f["text"], "emoji": f["emoji"]})
    return render_anomaly_report(grouped, asof, f"{BASE_URL}/anomaly-report")


def _halted_stocks_data():
    """현재 거래정지 종목 상세 — 이름/시장/정지 전 마지막가·날짜/최근 공시.
    get_ranking()은 이 종목들을 이미 걸러내므로, 여기서는 get_halted_codes()로
    별도 조회한다.

    거래정지 종목이 100개 넘어서, 종목마다 DART 공시를 '순차'로 부르면 1~2분씩
    걸렸음(실제 문제). (1) 조립 결과를 30분 캐시하고 (2) 느린 DART 공시 호출만
    스레드풀로 병렬화한다. DB(sqlite) 조회는 스레드 공유가 안전하지 않아 메인
    스레드에서 먼저 끝내고, 네트워크(DART) 호출만 병렬로 돌린다."""
    from concurrent.futures import ThreadPoolExecutor
    TTL = 1800  # 30분
    cached = _cache.get("halted_page")
    ts = _cache.get("halted_page_ts")
    # 콜드부팅 직후엔 get_halted_codes()가 아직 빈 채로 "0개" 페이지가 먼저 캐시될 수
    # 있고, 그 뒤 종목 스캔(halted_ts)이 나중에 끝나도 페이지 캐시 자체는 자기 30분
    # TTL만 보고 그대로 "0개"를 계속 서빙하는 문제가 실제 있었음. 종목 스캔이 페이지
    # 캐시보다 더 최근이면(=스캔이 나중에 갱신됨) 자기 TTL과 무관하게 새로 조립한다.
    halted_ts = _cache.get("halted_ts")
    stale_by_rescan = (halted_ts is not None and ts is not None
                       and halted_ts.timestamp() > ts)
    if cached is not None and ts is not None and (time.time() - ts) < TTL and not stale_by_rescan:
        return cached

    halted = get_halted_codes()
    if not halted:
        _cache["halted_page"] = []
        _cache["halted_page_ts"] = time.time()
        return []
    m = _cache.get("master")
    if m is None:
        m = _cache["master"] = build_master()

    # 1) 메인 스레드에서 이름/시장/정지 전 마지막가(DB) 먼저 — 빠르고 네트워크 없음.
    conn = _conn()
    base = []
    for code in halted:
        hit = m[m["code"] == code]
        name = hit.iloc[0]["name"] if len(hit) else _name_of(code)
        market = hit.iloc[0]["market"] if len(hit) else None
        # 거래정지 중엔 시세제공사가 마지막 체결가를 그대로 매일 반복해서 내려주는
        # 경우가 있어(거래량 0), 단순 "최신 row"는 정지 시작일이 아니라 오늘 날짜처럼
        # 보여 오해를 부른다 — 실제 거래(volume>0)가 있었던 마지막 날을 정지 시작일로 본다.
        row = conn.execute(
            "SELECT close,date FROM daily_prices WHERE code=? AND close IS NOT NULL "
            "AND volume>0 ORDER BY date DESC LIMIT 1", (code,)).fetchone()
        if not row:
            row = conn.execute(
                "SELECT close,date FROM daily_prices WHERE code=? AND close IS NOT NULL "
                "ORDER BY date DESC LIMIT 1", (code,)).fetchone()
        last_price, last_date = (row[0], row[1]) if row else (None, None)
        base.append({"code": code, "name": name, "market": market,
                     "last_price": last_price, "last_date": last_date})
    conn.close()

    # 2) 느린 DART 공시 호출만 병렬로(6시간 캐시라 웜이면 즉시 반환됨).
    with ThreadPoolExecutor(max_workers=16) as ex:
        discs = list(ex.map(lambda c: api_disclosures(c).get("items", [])[:3],
                            [b["code"] for b in base]))
    for b, d in zip(base, discs):
        b["disclosures"] = d

    base.sort(key=lambda x: x["last_date"] or "", reverse=True)
    _cache["halted_page"] = base
    _cache["halted_page_ts"] = time.time()
    return base


@app.get("/api/halted")
def api_halted():
    from content import render_halted_stocks
    html = render_halted_stocks(_halted_stocks_data(), get_asof(), f"{BASE_URL}/halted")
    return {"html": _extract_body(html)}


@app.get("/halted", response_class=HTMLResponse)
def halted_page():
    from content import render_halted_stocks
    return render_halted_stocks(_halted_stocks_data(), get_asof(), f"{BASE_URL}/halted")


def _anomaly_count(rk):
    return sum(1 for r in rk if r.get("flags"))


@app.get("/monthly", response_class=HTMLResponse)
def monthly_health():
    from content import render_monthly_health
    rk = get_ranking()
    asof = get_asof()
    movers_up, movers_down = _rank_movers(rk, get_ranking_asof(30))
    return render_monthly_health(rk, _anomaly_count(rk), asof, f"{BASE_URL}/monthly", movers_up, movers_down)


@app.get("/api/monthly")
def api_monthly_health():
    from content import render_monthly_health
    rk = get_ranking()
    asof = get_asof()
    movers_up, movers_down = _rank_movers(rk, get_ranking_asof(30))
    html = render_monthly_health(rk, _anomaly_count(rk), asof, f"{BASE_URL}/monthly", movers_up, movers_down)
    return {"html": _extract_body(html)}


def _earnings_items():
    conn = _conn()
    items = db.get_recent_disclosures(conn, limit=40)
    conn.close()
    for it in items:
        it["name"] = _name_of(it["code"])
    return items


# 2026년 KRX 휴장일(설날/추석/대체공휴일 포함) - 매년 갱신 필요.
# 출처: upward-curve.co.kr 2026년 주식시장 휴장일 정리(2차 자료) - 공식 KRX 공지로
# 한 번 더 대조 확인 권장. 주말은 now.weekday()로 별도 처리하므로 여기엔 평일 휴장일만.
KR_MARKET_HOLIDAYS_2026 = {
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18",
    "2026-03-02", "2026-05-01", "2026-05-05", "2026-05-25",
    "2026-06-03", "2026-07-17", "2026-08-17", "2026-09-24", "2026-09-25",
    "2026-10-05", "2026-10-09", "2026-12-25", "2026-12-31",
    # 2026-07-17: 제헌절. 2008년 공휴일에서 빠졌다가 '공휴일에 관한 법률' 개정으로
    # 2026년부터 18년 만에 법정공휴일 재지정 — 관공서·금융기관(증시 포함) 휴장.
}


def _is_market_holiday(now) -> bool:
    if now.weekday() >= 5:  # 토(5)/일(6)
        return True
    return now.strftime("%Y-%m-%d") in KR_MARKET_HOLIDAYS_2026


def _earning_tag(pct):
    if pct is None:
        return ""
    if pct >= 20:
        return " (어닝서프라이즈 \U0001F389)"
    if pct <= -20:
        return " (어닝쇼크 \U0001F631)"
    return ""


def _overnight_us_indices():
    """장전 브리핑/카드뉴스 공용: 나스닥/S&P500/원달러 + 코스피/코스닥 당일 등락 원시 수치.
    코스피·코스닥은 인스타 표지 헤드라인에서 '오늘 코스피 급락' 같은, 실적(분기 전 데이터)
    보다 훨씬 시의성 있는 소재로 쓰려고 추가함. get_market_indices()는 백그라운드 캐시라
    일회성 배치에선 빈 값이 나올 수 있어 동기 fetch_indices()를 직접 호출한다(야후 장애
    시 조용히 생략). 못 가져오면 None."""
    try:
        import market_indices
        ix = market_indices.fetch_indices()
    except Exception:
        return None
    if not ix:
        return None
    nasdaq, sp500 = ix.get("nasdaq"), ix.get("sp500")
    if not (nasdaq or sp500):
        return None
    return {"nasdaq": nasdaq, "sp500": sp500, "usdkrw": ix.get("usdkrw"),
            "kospi": ix.get("kospi"), "kosdaq": ix.get("kosdaq")}


def _kr_index_streak(key):
    """코스피/코스닥의 최근 며칠 연속 등락 흐름 — '며칠 하락하다 오늘 반등?',
    '상승장에서 오늘 조정?' 같은 카드 헤드라인용. 최근 6거래일 종가로 일별
    등락률 5개를 계산해 반환(마지막 값이 오늘). 실패하면 None."""
    try:
        import market_indices
        hist = market_indices.fetch_history(key, "1mo")
    except Exception:
        return None
    pts = hist["points"] if hist else []
    if len(pts) < 6:
        return None
    closes = [p["c"] for p in pts[-6:]]
    rets = [(closes[i] / closes[i - 1] - 1) * 100 for i in range(1, len(closes)) if closes[i - 1]]
    if len(rets) < 5:
        return None
    return {"name": hist["name"], "returns": rets}


def _overnight_us_line():
    """위 원시 수치를 뉴스레터용 한 줄 텍스트로 포맷."""
    ix = _overnight_us_indices()
    if not ix:
        return None
    parts = []
    for key in ("nasdaq", "sp500"):
        d = ix.get(key)
        if d and d.get("chg_pct") is not None:
            parts.append(f"{d['name']} {d['chg_pct']:+.1f}%")
    if not parts:
        return None
    usd = ix.get("usdkrw")
    fx = f" / 원달러 {usd['price']:,.1f}원" if usd and usd.get("price") else ""
    return "\U0001F30F 간밤 미국증시 — " + " · ".join(parts) + fx


def _weekly_index_line():
    """주간 마무리용: 코스피·코스닥 주간 등락률 한 줄(1개월 히스토리에서 ~5거래일 전 대비).
    데이터 못 가져오면 None."""
    try:
        import market_indices
        parts = []
        for key in ("kospi", "kosdaq"):
            hist = market_indices.fetch_history(key, "1mo")
            pts = hist["points"] if hist else []
            if len(pts) >= 6 and pts[-6]["c"]:
                chg = (pts[-1]["c"] / pts[-6]["c"] - 1) * 100
                parts.append(f"{hist['name']} {chg:+.1f}%")
        if not parts:
            return None
        return "\U0001F4CA 이번주 지수 — " + " · ".join(parts)
    except Exception:
        return None


def _period_movers(conn, codes, offset=1, n=3):
    """N거래일 전 종가 대비 급등·급락 TOP N (ranking 유니버스 한정).
    offset=1이면 전거래일 대비(일간), offset=5면 1주일 전(주간) 비교."""
    dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM daily_prices WHERE close IS NOT NULL "
        "ORDER BY date DESC LIMIT ?", (offset + 1,)).fetchall()]
    if len(dates) <= offset:
        return [], [], None
    d_now, d_prev = dates[0], dates[offset]
    now_map = dict(conn.execute(
        "SELECT code,close FROM daily_prices WHERE date=? AND close IS NOT NULL", (d_now,)).fetchall())
    prev_map = dict(conn.execute(
        "SELECT code,close FROM daily_prices WHERE date=? AND close IS NOT NULL", (d_prev,)).fetchall())
    codeset = set(codes)
    changes = []
    for code, close in now_map.items():
        if code not in codeset:
            continue
        p = prev_map.get(code)
        if p:
            changes.append((code, (close / p - 1) * 100))
    changes.sort(key=lambda x: x[1])
    losers = changes[:n]
    gainers = list(reversed(changes[-n:]))
    return gainers, losers, d_now


def _score_movers(rk_now, rk_past, n=3):
    """지난주 대비 종합점수(팩터 스코어) 급상승·급하락 TOP N."""
    past_score = {r["code"]: r["score"] for r in rk_past}
    diffs = []
    for r in rk_now:
        ps = past_score.get(r["code"])
        if ps is None:
            continue
        diffs.append({"code": r["code"], "name": r["name"], "score": r["score"],
                      "prev_score": ps, "score_change": round(r["score"] - ps, 1)})
    up = sorted([d for d in diffs if d["score_change"] > 0],
                key=lambda d: d["score_change"], reverse=True)[:n]
    down = sorted([d for d in diffs if d["score_change"] < 0],
                  key=lambda d: d["score_change"])[:n]
    return up, down


def _trading_day_ordinal(now):
    """이번 달 1일부터 오늘까지(포함) 개장일수 — '이달의 기업 종합검진'에서 몇 번째
    영업일인지로 오늘 보여줄 순위를 정하는 데 씀."""
    from datetime import timedelta
    d = now.replace(day=1)
    count = 0
    while d.date() <= now.date():
        if not _is_market_holiday(d):
            count += 1
        d += timedelta(days=1)
    return count


def _company_of_the_day(rk, now):
    """랭킹 1~50위 전체를 대상으로 노출 순서를 월 단위 시드로 셔플해서 영업일마다
    하나씩 보여준다. 등수 그대로(1→20위) 고정 순서로 돌리면, 종합점수가 연간
    재무제표 기준이라 거의 안 바뀌는 탓에 매달 똑같은 순서로 반복되는 문제가
    있었음(사용자 피드백) — 셔플 시드를 '연-월'로 고정해 그 달 안에서는 중복 없이
    한 바퀴를 돌되(영업일이 최대 23일 정도라 50개 중 절반도 못 돌지만 매달 다른
    절반이 나옴), 다음 달엔 다른 순서로 다시 섞이게 한다(테마/이상신호 로테이션과
    동일한 날짜시드 패턴)."""
    pool = rk[:50]
    if not pool:
        return None
    import random
    month_seed = random.Random(now.strftime("%Y-%m"))
    order = pool[:]
    month_seed.shuffle(order)
    ordinal = _trading_day_ordinal(now)
    return order[(ordinal - 1) % len(order)]


def _theme_examples(tmap, rk_by_code, no, n=3):
    """테마 구성종목 중 시총 상위 n개 이름(블로그 초안용 예시 종목)."""
    t = tmap.get("themes", {}).get(no)
    if not t:
        return []
    pool = [rk_by_code[c] for c in t.get("codes", []) if c in rk_by_code]
    pool.sort(key=lambda r: r.get("marcap", 0), reverse=True)
    return [r["name"] for r in pool[:n]]


def _blog_draft_data():
    """'장 열리기전 체크포인트'의 원시(구조화) 데이터만 계산 — 텍스트 조립은 안 함.
    뉴스레터 텍스트(_blog_draft_text)와 인스타 카드뉴스 생성기가 이 함수를 공유해서
    쓴다(카드뉴스는 완성된 텍스트를 다시 정규식으로 파싱하는 대신 이 구조화 데이터를
    바로 받아씀 — 포맷이 바뀌어도 안 깨지고, 이모지 대신 원시 수치라 폰트 의존도 없음).
    주말/공휴일(휴장일)에는 is_holiday=True만 반환."""
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    if _is_market_holiday(now):
        return {"date": now, "is_holiday": True}

    conn = _conn()
    # 최근 1개월 이내 공시만 — 그보다 오래된 건 '오늘 브리핑'에 넣기엔 철 지난 소식이라
    # 제외(넉넉한 풀에서 가져온 뒤 날짜로 거른다. limit=8이면 공시 뜸한 날 오래된 것까지
    # 끌려올 수 있어 limit을 키움).
    one_month_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    disclosures = [d for d in db.get_recent_disclosures(conn, limit=60)
                   if d["disclosed_date"] >= one_month_ago]
    rk = get_ranking()
    codes = [r["code"] for r in rk]
    gainers, losers, movers_date = _period_movers(conn, codes, offset=1, n=3)
    if _cache.get("theme_perf") is None:
        from factor.themes import compute_theme_perf
        _cache["theme_perf"] = compute_theme_perf(conn, get_tmap())
    if _cache.get("theme_groups") is None:
        from factor.themes import compute_group_hierarchy
        if _cache["master"] is None:
            _cache["master"] = build_master()
        _cache["theme_groups"] = compute_group_hierarchy(conn, get_tmap(), master=_cache["master"])
    conn.close()

    for it in disclosures:
        it["name"] = _name_of(it["code"])
    tmap = get_tmap()
    rk_by_code = {r["code"]: r for r in rk}

    earnings = []
    for it in disclosures[:5]:
        ni = it.get("ni_yoy")
        tag = "surprise" if (ni is not None and ni >= 20) else "shock" if (ni is not None and ni <= -20) else None
        earnings.append({"name": it["name"], "code": it["code"], "year": it["year"],
                          "quarter": it["quarter"], "rev_yoy": it.get("rev_yoy"),
                          "rev_qoq": it.get("rev_qoq"), "ni_yoy": ni, "tag": tag})

    import random
    day_seed = random.Random(now.strftime("%Y-%m-%d"))  # 날짜로 시드 고정 — 같은 날 안에서는
                                                          # 안정적이고, 날마다 다르게 로테이션

    all_anomalies = [{"name": r["name"], "code": r["code"], **f}
                      for r in rk for f in (r.get("flags") or [])]
    reds = [a for a in all_anomalies if a["emoji"] == "\U0001F534"]
    yellows = [a for a in all_anomalies if a["emoji"] != "\U0001F534"]
    # 빨강(고심각도)은 '다양성'을 이유로 절대 누락하지 않음 — 최대 5개까지 전부 노출.
    # 노랑은 날짜별로 로테이션해서 매일 다른 종목이 섞여 보이게(항상 2개까지).
    reds = reds[:5]
    yellows_shuffled = yellows[:]
    day_seed.shuffle(yellows_shuffled)
    anomalies = reds + yellows_shuffled[:2]

    mids_all = [m for maj in _cache["theme_groups"] for m in maj["mids"]
                if m.get("used", 0) >= 3 and m.get("theme_count", 0) >= 1
                and m.get("ret_1m") is not None]
    # 상승 테마만 모아서 보여주면 반쪽짜리 시황이라, 상승 2개(1위 고정 + 나머지는
    # 상위권에서 날짜별 로테이션) · 하락 2개(동일 패턴)를 같이 보여준다. 1위(가장
    # 화제성 있는 상승 테마)만 고정하고 나머지는 매번 순위 그대로면 1개월 수익률이
    # 완만하게 바뀌는 지표 특성상 며칠씩 똑같은 테마만 나오게 돼서 로테이션 유지.
    risers = sorted([m for m in mids_all if m["ret_1m"] >= 0],
                     key=lambda m: m["ret_1m"], reverse=True)
    fallers = sorted([m for m in mids_all if m["ret_1m"] < 0], key=lambda m: m["ret_1m"])

    def _pick_two(pool):
        top_pool = pool[:6]
        picked = top_pool[:1]
        rest = top_pool[1:]
        day_seed.shuffle(rest)
        picked += rest[:1]
        return picked

    themes_pick = _pick_two(risers) + _pick_two(fallers)

    themes = []
    for m in themes_pick:
        sub = [t for t in m["themes"] if t.get("used", 0) >= 3 and t["count"] >= 8]
        sub.sort(key=lambda t: (t["ret_1m"] is not None, t["ret_1m"]), reverse=True)
        sub_out = []
        for t in sub[:3]:
            examples = _theme_examples(tmap, rk_by_code, t["no"], 3)
            sub_out.append({"name": t["name"], "ret_1m": t["ret_1m"], "examples": examples})
        themes.append({"mid": m["mid"], "ret_1m": m["ret_1m"], "sub": sub_out})

    return {
        "date": now, "is_holiday": False,
        "us_indices": _overnight_us_indices(),
        "kr_trend": {"kospi": _kr_index_streak("kospi"), "kosdaq": _kr_index_streak("kosdaq")},
        "movers_date": movers_date, "gainers": gainers, "losers": losers,
        "earnings": earnings, "anomalies": anomalies, "themes": themes,
        "featured": _company_of_the_day(rk, now),
    }


_DIM_ORDER = [("value", "밸류에이션"), ("profit", "수익성"), ("safety", "안정성"), ("growth", "성장성")]


def _stars_text(n):
    n = n or 0
    return "★" * n + "☆" * (5 - n)


def _featured_lines(f):
    """'이달의 기업 종합검진' 섹션 — 랭킹 1~20위를 영업일마다 하나씩 순서대로 보여주는
    우리만의 차별 콘텐츠(전 종목 스크리닝·회계감사의견까지 보여주는 게 강점이라,
    그 강점을 매일 실제 종목 하나로 직접 보여주는 섹션)."""
    # "종합랭킹 N위"를 헤드라인에 쓰면 매수 추천 순위처럼 오해할 수 있어(사용자 피드백) —
    # 건강검진 결과처럼 읽히는 점수를 앞세우고, 등수는 참고용으로만 괄호에 덧붙인다.
    dims = f["dims"]
    lines = [f"\U0001F3E5 이달의 기업 종합검진 — {f['name']}({f['code']}) 건강점수 {f['score']:.1f}점"
             f" (참고용 건강점수 랭킹 {f['rank']}위)"]
    for key, label in _DIM_ORDER:
        d_ = dims[key]
        lines.append(f"- {label} {_stars_text(d_['stars'])} {d_['label']}: {d_['text']}")
    if dims.get("overall_text"):
        lines.append(dims["overall_text"])
    lines.append("* 건강점수는 밸류에이션·수익성·안정성·성장성을 같은 업종 내 백분위로 환산한 "
                 "참고 지표로, 매수·매도 추천이 아닙니다.")
    lines.append("")
    return lines


def _rot(seed_key, options):
    """날짜+슬롯 시드로 옵션 중 하나 고정 선택 — card_templates._rot과 같은 패턴.
    매일 인트로·섹션 제목이 똑같으면 '자동생성 템플릿'처럼 보여 애드센스에도 불리해서,
    본문 문구를 날짜별로 로테이션한다(같은 날엔 안정적, 날마다 다름). 슬롯명을 다르게
    줘서 같은 날 여러 문구가 전부 같은 인덱스로 몰리지 않게 함."""
    return random.Random(seed_key).choice(options)


def _bonus_blocks(seed):
    """장전 브리핑에 매일 하나씩 랜덤으로 끼워넣을 '오늘의 픽' 후보 블록들. 전부 이미 가진
    랭킹 데이터(건강점수·PER·배당·부채비율·ROE·매출성장·점수변동)에서 뽑은 큐레이션이라
    추가 수집 없이 콘텐츠 다양성만 늘린다 — 매일 같은 6개 섹션만 반복되면 자동생성 티가
    나므로. 매수 추천이 아니라 정보/교육용(공통 면책 적용). 데이터 부족한 픽은 자동 제외.
    이모지는 코어 섹션(🌏📈📊🚩🔥🏥)과 겹치지 않게 골랐다."""
    rk = get_ranking()
    blocks = {}

    # 저평가 우량주 (PER 낮고 건강점수 높은)
    vp = sorted([r for r in rk if r["per"] and 0 < r["per"] <= 15],
                key=lambda r: r["score"], reverse=True)
    if len(vp) >= 3:
        b = [_rot(f"{seed}|h_value", [
            "\U0001F48E 저평가 우량주 픽 — 건강점수 높고 PER 낮은 종목",
            "\U0001F48E 오늘의 저평가 우량주 (건강점수·PER 기준)",
            "\U0001F48E 가치+퀄리티 픽 — 싸고 튼튼한 종목",
        ])]
        for r in vp[:4]:
            b.append(f"- {r['name']}({r['code']}): 건강점수 {r['score']:.1f} · PER {r['per']:.1f} · PBR {r['pbr']:.2f}")
        blocks["value_pick"] = b

    # 고배당주
    dp = sorted([r for r in rk if r.get("div_yield") and 0 < r["div_yield"] <= 20],
                key=lambda r: r["div_yield"], reverse=True)
    if len(dp) >= 3:
        b = [_rot(f"{seed}|h_div", [
            "\U0001F4B0 고배당주 픽 — 배당수익률 상위 종목",
            "\U0001F4B0 오늘의 고배당 종목 (배당수익률 기준)",
            "\U0001F4B0 배당 매력 픽 — 배당수익률 높은 종목",
        ])]
        for r in dp[:4]:
            b.append(f"- {r['name']}({r['code']}): 배당수익률 {r['div_yield']:.2f}% · 건강점수 {r['score']:.1f}")
        blocks["dividend_pick"] = b

    # 재무 안전주 (부채비율 낮은 우량)
    sp = sorted([r for r in rk if r["debt_ratio"] is not None and r["debt_ratio"] <= 50],
                key=lambda r: r["score"], reverse=True)
    if len(sp) >= 3:
        b = [_rot(f"{seed}|h_safe", [
            "\U0001F6E1 재무 안전주 픽 — 부채비율 낮은 우량 종목",
            "\U0001F6E1 오늘의 안전주 (부채비율 낮은 종목)",
            "\U0001F6E1 튼튼한 재무 픽 — 빚 적고 점수 높은 종목",
        ])]
        for r in sp[:4]:
            b.append(f"- {r['name']}({r['code']}): 부채비율 {r['debt_ratio']:.0f}% · 건강점수 {r['score']:.1f}")
        blocks["safety_pick"] = b

    # 수익성 상위 (ROE)
    pp = sorted([r for r in rk if r["roe"] is not None and 0 < r["roe"] <= 80],
                key=lambda r: r["roe"], reverse=True)
    if len(pp) >= 3:
        b = [_rot(f"{seed}|h_profit", [
            "\U0001F4B8 수익성 픽 — ROE 높은 종목",
            "\U0001F4B8 오늘의 고ROE 종목 (자본 효율 상위)",
            "\U0001F4B8 돈 잘 버는 픽 — ROE 상위 종목",
        ])]
        for r in pp[:4]:
            opm = f" · 영업이익률 {r['op_margin']:.1f}%" if r.get("op_margin") is not None else ""
            b.append(f"- {r['name']}({r['code']}): ROE {r['roe']:.1f}%{opm}")
        blocks["profit_pick"] = b

    # 매출 급성장
    gp = sorted([r for r in rk if r.get("rev_growth") is not None and 0 < r["rev_growth"] <= 300],
                key=lambda r: r["rev_growth"], reverse=True)
    if len(gp) >= 3:
        b = [_rot(f"{seed}|h_growth", [
            "\U0001F331 고성장 픽 — 매출 급증 종목",
            "\U0001F331 오늘의 매출 성장주 (전년 대비)",
            "\U0001F331 성장 픽 — 매출 증가율 상위 종목",
        ])]
        for r in gp[:4]:
            b.append(f"- {r['name']}({r['code']}): 매출 +{r['rev_growth']:.1f}% · 건강점수 {r['score']:.1f}")
        blocks["growth_pick"] = b

    # 종합점수 급상승 (최근 ~1주 대비)
    try:
        up, _down = _score_movers(rk, get_ranking_asof(7), n=4)
    except Exception:
        up = []
    if len(up) >= 3:
        b = [_rot(f"{seed}|h_scoreup", [
            "\U00002728 건강점수 급상승 픽 — 최근 점수가 오른 종목",
            "\U00002728 오늘의 점수 상승 종목 (최근 1주 대비)",
            "\U00002728 개선세 픽 — 종합점수가 오른 종목",
        ])]
        for m in up:
            b.append(f"- {m['name']}({m['code']}): {m['prev_score']:.1f} → {m['score']:.1f}점 ({m['score_change']:+.1f})")
        blocks["scoreup_pick"] = b

    return blocks


def _blog_draft_text():
    """'장 열리기전 체크포인트' 블로그 초안(제목+본문) 생성.
    네이버 블로그 자동 포스팅 API는 2020년에 종료되어(직접 확인함) 발행은 수동으로
    해야 하지만, 초안은 매일 최신 데이터로 자동 완성해 복사만 하면 되게 한다."""
    data = _blog_draft_data()
    now = data["date"]
    title = f"{now.month}월 {now.day}일 장전 체크포인트 | 국내증시 브리핑"

    if data["is_holiday"]:
        return title, "오늘은 국내증시 휴장일이라 특별히 정리할 소식이 없어요. 다음 개장일에 다시 올게요!"

    gainers, losers, movers_date = data["gainers"], data["losers"], data["movers_date"]
    seed = now.strftime("%Y-%m-%d")

    intro = _rot(f"{seed}|intro", [
        ["좋은 아침입니다 \U0001F44B 오늘 장 시작 전에 체크하면 좋을 국내증시 소식,",
         "코스피·코스닥 실적 발표랑 특징테마 위주로 정리해봤어요."],
        ["오늘도 좋은 아침이에요 \U0001F44B 장 열리기 전에 훑어두면 좋은 국내증시 소식들,",
         "어제 급등락·실적 발표·주도테마 흐름 위주로 골라 정리했어요."],
        ["반가워요 \U0001F44B 오늘 국내 증시, 시작 전에 핵심만 빠르게 짚어볼게요.",
         "어제 움직임·실적 발표·강세테마 순서로 담았어요."],
        ["장 시작 전 5분 브리핑입니다 \U0001F44B 오늘 꼭 체크할 국내증시 포인트,",
         "코스피·코스닥 급등락과 실적·테마 위주로 정리했어요."],
    ])
    # 각 섹션을 '블록'으로 만들어 dict에 담은 뒤, 날짜별로 고른 순서 룰셋대로 조립한다.
    # 문구 로테이션(_rot 헤더)에 더해 '순서'까지 매일 달라져서 구조 자체가 반복되지 않게
    # 함 — 종목 페이지처럼 매일 똑같은 골격이면 자동생성 티가 나서 애드센스에도 불리.
    # (featured '이달의 기업 종합검진'은 마무리 성격 + 뒤에 CTA가 붙어서 항상 맨 끝 고정.)
    blocks = {}

    ix = data["us_indices"]
    if ix:
        parts = [f"{ix[k]['name']} {ix[k]['chg_pct']:+.1f}%" for k in ("nasdaq", "sp500")
                 if ix.get(k) and ix[k].get("chg_pct") is not None]
        if parts:
            usd = ix.get("usdkrw")
            fx = f" / 원달러 {usd['price']:,.1f}원" if usd and usd.get("price") else ""
            blocks["market"] = [
                "\U0001F30F 간밤 미국증시 — " + " · ".join(parts) + fx,
                "(국내 증시는 간밤 미국장 흐름에 영향을 받는 편이에요.)",
            ]

    if gainers or losers:
        _n = len(gainers) or len(losers)
        b = [_rot(f"{seed}|movers", [
            f"\U0001F4C8 어제({movers_date}) 급등·급락 TOP{_n}",
            f"\U0001F4C8 어제({movers_date}) 가장 많이 움직인 종목 TOP{_n}",
            f"\U0001F4C8 어제({movers_date}) 급등·급락 상위 {_n}종목",
        ])]
        for code, pct in gainers:
            b.append(f"- (급등) {_name_of(code)}({code}): {pct:+.1f}%")
        for code, pct in losers:
            b.append(f"- (급락) {_name_of(code)}({code}): {pct:+.1f}%")
        blocks["movers"] = b

    if data["earnings"]:
        b = [_rot(f"{seed}|earn", [
            "\U0001F4CA 실적 발표 브리핑 (어닝서프라이즈·어닝쇼크 체크)",
            "\U0001F4CA 최근 실적 발표 — 서프라이즈와 쇼크 체크",
            "\U0001F4CA 실적 시즌 체크 (어닝서프라이즈·어닝쇼크)",
        ]), "(최근 1개월 내 실적 발표 기준 · 전년동기대비)"]
        for it in data["earnings"]:
            rev, rev_q, ni = it.get("rev_yoy"), it.get("rev_qoq"), it.get("ni_yoy")
            if rev is not None:
                rev_tag = f"매출 {rev:+.1f}%"
            elif rev_q is not None:
                rev_tag = f"매출(전분기) {rev_q:+.1f}%"
            else:
                rev_tag = "매출 데이터 부족(금융업 등 업종 특성)"
            # 어닝서프라이즈/쇼크 판정은 매출보다 이익이 핵심이라 순이익에 태그를 붙인다.
            ni_tag = f" · 순이익 {ni:+.1f}%{_earning_tag(ni)}" if ni is not None else ""
            b.append(f"- {it['name']}({it['code']}) {it['year']}년 {it['quarter']}분기 실적: {rev_tag}{ni_tag}")
        blocks["earnings"] = b

    if data["anomalies"]:
        b = [_rot(f"{seed}|anom", [
            "\U0001F6A9 조심해서 봐야 할 이상신호 종목",
            "\U0001F6A9 재무 이상신호가 켜진 종목",
            "\U0001F6A9 한 번 더 확인해볼 이상신호 종목",
        ])]
        for a in data["anomalies"]:
            b.append(f"- {a['name']}({a['code']}) {a['label']}: {a['text']}")
        blocks["anomaly"] = b

    if data["themes"]:
        b = [_rot(f"{seed}|theme", [
            "\U0001F525 요즘 주도테마 · 특징테마 (최근 1개월 수익률)",
            "\U0001F525 지금 뜨는 테마 · 특징테마 (최근 1개월)",
            "\U0001F525 최근 강세 테마 흐름 (1개월 수익률)",
        ])]
        for m in data["themes"]:
            b.append(f"- {m['mid']}: {m['ret_1m']:+.1f}%")
            for t in m["sub"]:
                ex = f" (예: {', '.join(t['examples'])})" if t["examples"] else ""
                b.append(f"  - {t['name']}: {t['ret_1m']:+.1f}%{ex}")
        blocks["theme"] = b

    # 미국증시·급등락은 시황 파악에 필수라는 요청으로 매일 고정 — 맨 앞에 이 순서 그대로
    # 두고 로테이션 대상에서 뺀다. 나머지(실적/이상신호/테마 + 오늘의 픽)만 순서를 섞어서
    # 다양성을 준다. featured(이달의 기업 종합검진)는 이 뒤에 별도로 고정 배치(항상 마지막).
    fixed_head = [n for n in ("market", "movers") if n in blocks]

    order = _rot(f"{seed}|order", [
        ["earnings", "anomaly", "theme"],
        ["theme", "earnings", "anomaly"],
        ["anomaly", "theme", "earnings"],
        ["theme", "anomaly", "earnings"],
        ["earnings", "theme", "anomaly"],
    ])
    present = fixed_head + [n for n in order if n in blocks]

    # '오늘의 픽' 후보 중 하루 하나를 랜덤으로 골라 끼워넣는다 — 위치는 고정 헤더(미국증시·
    # 급등락) 뒤에서만 랜덤(헤더보다 앞에 오면 안 되므로).
    bonus = _bonus_blocks(seed)
    if bonus:
        pick = _rot(f"{seed}|bonuspick", sorted(bonus.keys()))
        blocks[pick] = bonus[pick]
        pos = random.Random(f"{seed}|bonuspos").randint(len(fixed_head), len(present))
        present.insert(pos, pick)

    lines = [intro[0], intro[1], ""]
    for name in present:
        lines += blocks[name]
        lines.append("")

    if data.get("featured"):
        lines += _featured_lines(data["featured"])

    lines.append(f"\U0001F449 위에 나온 종목들 재무제표·회계감사의견(적정/한정)까지, "
                  f"머니체크업에서 무료로 바로 확인하세요.")
    lines.append(f"전 종목 스크리닝·이상신호도 함께 보실 수 있어요 {BASE_URL}/")
    lines.append("")
    lines.append("※ 이 글은 공개 데이터를 정리한 정보 제공용 콘텐츠이며, 특정 종목에 대한")
    lines.append("매수·매도 추천이 아닙니다. 투자 판단과 책임은 본인에게 있습니다.")
    lines.append("")
    lines.append("#국내증시 #코스피 #코스닥 #오늘의증시 #장전브리핑 #실적발표 "
                  "#어닝서프라이즈 #특징주 #특징테마 #머니체크업")
    return title, "\n".join(lines)


def _weekly_wrap_data():
    """'주간 마무리'의 원시(구조화) 데이터만 계산 — _blog_draft_data()의 주간판.
    뉴스레터 텍스트(_weekly_wrap_text)와 주간 인스타 카드뉴스 생성기가 이 함수를
    공유한다(일간판과 동일한 이유 — 완성 텍스트를 다시 파싱하지 않기 위함).
    토요일 아침 전용(평일 브리핑과 별개). 금요일 종가까지 반영된 데이터로 만드므로
    (daily-prices.yml이 금요일 저녁에 갱신) 당일 장이 아직 안 열려 생기던
    '반쪽짜리 주간 요약' 문제를 피한다."""
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)

    conn = _conn()
    rk = get_ranking()
    codes = [r["code"] for r in rk]
    week_gainers, week_losers, week_date = _period_movers(conn, codes, offset=5, n=3)
    if _cache.get("theme_perf") is None:
        from factor.themes import compute_theme_perf
        _cache["theme_perf"] = compute_theme_perf(conn, get_tmap())
    conn.close()

    rk_past = get_ranking_asof(7)
    score_up, score_down = _score_movers(rk, rk_past)
    strong_themes = [t for t in _cache["theme_perf"]
                     if t.get("priced", 0) >= 5 and t.get("ret_1m") is not None]
    strong_themes.sort(key=lambda t: t["ret_1m"], reverse=True)
    strong_themes = strong_themes[:5]
    rk_by_code = {r["code"]: r for r in rk}
    tmap = get_tmap()
    for t in strong_themes:
        t["examples"] = _theme_examples(tmap, rk_by_code, t["no"], 3)

    idx = []
    try:
        import market_indices
        for key in ("kospi", "kosdaq"):
            hist = market_indices.fetch_history(key, "1mo")
            pts = hist["points"] if hist else []
            if len(pts) >= 6 and pts[-6]["c"]:
                chg = (pts[-1]["c"] / pts[-6]["c"] - 1) * 100
                idx.append({"name": hist["name"], "chg": chg})
    except Exception:
        pass

    # 지금 재무 이상신호가 떠 있는 종목(주간 리포트에도 이 차별 섹션을 노출). '이번주 새로'는
    # 지난주 신호 상태를 따로 저장하지 않아 단정 못 하므로 '체크할'로 표현(허위 방지).
    anomalies = [{"name": r["name"], "code": r["code"], **f} for r in rk for f in (r.get("flags") or [])]
    anomalies.sort(key=lambda a: 0 if a["emoji"] == "\U0001F534" else 1)

    return {
        "date": now, "is_holiday": False, "week_date": week_date,
        "idx": idx,
        "gainers": [{"name": _name_of(c), "code": c, "pct": pct} for c, pct in week_gainers],
        "losers": [{"name": _name_of(c), "code": c, "pct": pct} for c, pct in week_losers],
        "strong_themes": strong_themes,
        "anomalies": anomalies[:3],
        "score_up": score_up, "score_down": score_down,
    }


def _weekly_wrap_text(data=None):
    """토요일 아침 전용 '주간 마무리' 메일(평일 브리핑과 별개)."""
    data = data if data is not None else _weekly_wrap_data()
    now = data["date"]
    title = f"{now.month}월 {now.day}일 이번주 국내증시 마무리 | 머니체크업"

    lines = [
        "이번주도 고생 많으셨어요 \U0001F44B 이번주 국내증시, 이것만 보고 가세요.",
        "",
    ]

    if data["idx"]:
        idx_line = "\U0001F4CA 이번주 지수 — " + " · ".join(
            f"{i['name']} {i['chg']:+.1f}%" for i in data["idx"])
        lines.append(idx_line)
        lines.append("")

    if data["gainers"] or data["losers"]:
        lines.append("\U0001F4C8 금주 가장 많이 오른 종목 · 하락한 종목")
        for g in data["gainers"]:
            lines.append(f"- (상승) {g['name']}({g['code']}): {g['pct']:+.1f}%")
        for l in data["losers"]:
            lines.append(f"- (하락) {l['name']}({l['code']}): {l['pct']:+.1f}%")
        lines.append("")

    if data["strong_themes"]:
        lines.append("\U0001F525 이번주 강세 테마 TOP5")
        for t in data["strong_themes"]:
            lines.append(f"- {t['name']}: {t['ret_1m']:+.1f}%")
        lines.append("")

    if data["anomalies"]:
        lines.append("\U0001F6A9 이번주 체크할 이상신호 종목")
        for a in data["anomalies"]:
            lines.append(f"- {a['name']}({a['code']}) {a['label']}: {a['text']}")
        lines.append("")

    if data["score_up"]:
        lines.append("\U0001F4C8 이번주 종합점수 급상승 종목")
        for m in data["score_up"]:
            lines.append(f"- {m['name']}({m['code']}): {m['prev_score']:.1f}점 → "
                         f"{m['score']:.1f}점 ({m['score_change']:+.1f})")
        lines.append("")

    if data["score_down"]:
        lines.append("\U0001F4C9 이번주 종합점수 급하락 종목")
        for m in data["score_down"]:
            lines.append(f"- {m['name']}({m['code']}): {m['prev_score']:.1f}점 → "
                         f"{m['score']:.1f}점 ({m['score_change']:+.1f})")
        lines.append("")

    lines.append(f"\U0001F449 위에 나온 종목들 재무제표·회계감사의견(적정/한정)까지, "
                  f"머니체크업에서 무료로 바로 확인하세요.")
    lines.append(f"전 종목 스크리닝·이상신호도 함께 보실 수 있어요 {BASE_URL}/")
    lines.append("")
    lines.append("※ 이 글은 공개 데이터를 정리한 정보 제공용 콘텐츠이며, 특정 종목에 대한")
    lines.append("매수·매도 추천이 아닙니다. 투자 판단과 책임은 본인에게 있습니다.")
    lines.append("")
    lines.append("#국내증시 #코스피 #코스닥 #주간증시 #이번주증시 #주간결산 "
                  "#강세테마 #실적발표 #특징주 #머니체크업")
    return title, "\n".join(lines)


@app.get("/internal/blog-draft")
def blog_draft(key: str = ""):
    """블로그 초안 + 오늘 생성된 인스타 카드뉴스·캡션을 zip으로 한 번에 다운로드.
    content_out/{오늘}/이 있으면(자동 생성 완료) 그 파일들을 그대로 묶어서 내려줘 —
    이러면 블로그 글과 카드가 실제로 같은 시점 데이터를 보여준다는 게 보장됨(이 함수가
    그때그때 새로 계산해서 텍스트만 내려주면 카드 생성 이후 시세가 바뀌어 숫자가
    어긋날 수 있음). content_out이 아직 없으면(휴장일 등) 예전처럼 텍스트만 즉석 생성."""
    expected = os.getenv("BLOG_DRAFT_KEY")
    if not expected or key != expected:
        raise HTTPException(404)
    import io
    import zipfile
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    day_dir = os.path.join("content_out", today_str)
    blog_path = os.path.join(day_dir, "blog_draft.txt")
    cards_dir = os.path.join(day_dir, "cards")

    if not os.path.isfile(blog_path):
        # 토요일엔 평일용 _blog_draft_text()를 그대로 쓰면 "휴장일이라 소식 없음"으로
        # 잘못 나옴(주간 마무리 대신) — 자동 생성이 아직 안 끝난 시점에 눌렀을 때의
        # 폴백이라 요일에 맞는 함수로 갈라줘야 함.
        is_saturday = datetime.now(KST).weekday() == 5
        title, body = _weekly_wrap_text() if is_saturday else _blog_draft_text()
        content = f"{title}\n{'=' * len(title)}\n\n{body}"
        data = ("﻿" + content).encode("utf-8")  # BOM: 메모장 한글 인코딩 오인식 방지
        fname = f"blog-draft-{datetime.now(KST).strftime('%m%d')}.txt"
        return Response(content=data, media_type="text/plain; charset=utf-8",
                         headers={"Content-Disposition": f'attachment; filename="{fname}"'})

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        with open(blog_path, "rb") as f:
            zf.writestr("blog_draft.txt", "﻿".encode("utf-8") + f.read())
        if os.path.isdir(cards_dir):
            for fn in sorted(os.listdir(cards_dir)):
                zf.write(os.path.join(cards_dir, fn), f"cards/{fn}")
    fname = f"blog-draft-{datetime.now(KST).strftime('%m%d')}.zip"
    return Response(content=buf.getvalue(), media_type="application/zip",
                     headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.get("/earnings-report", response_class=HTMLResponse)
def earnings_report():
    from content import render_earnings_report
    return render_earnings_report(_earnings_items(), f"{BASE_URL}/earnings-report")


@app.get("/api/earnings-report")
def api_earnings_report():
    from content import render_earnings_report
    html = render_earnings_report(_earnings_items(), f"{BASE_URL}/earnings-report")
    return {"html": _extract_body(html)}


@app.get("/api/earnings-recent")
def api_earnings_recent(n: int = 5):
    return {"items": _earnings_items()[:n]}


_CONTENT_OUT = os.path.join(os.path.dirname(__file__), "content_out")
_DATE_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")


def _insight_dates():
    """content_out/ 안에서 blog_draft.txt가 있는 날짜 폴더만 최신순으로 반환."""
    if not os.path.isdir(_CONTENT_OUT):
        return []
    dates = [d for d in os.listdir(_CONTENT_OUT)
             if _DATE_RE.match(d) and os.path.isfile(
                 os.path.join(_CONTENT_OUT, d, "blog_draft.txt"))]
    return sorted(dates, reverse=True)


def _read_insight(date_str):
    """blog_draft.txt를 (제목, 본문)으로 분리. 첫 줄=제목, '===='밑줄 이후=본문."""
    path = os.path.join(_CONTENT_OUT, date_str, "blog_draft.txt")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    lines = raw.split("\n")
    title = lines[0].strip() if lines else date_str
    # 둘째 줄이 '===='류 밑줄이면 건너뛰고, 그 뒤 빈 줄들도 정리
    body_start = 1
    if len(lines) > 1 and set(lines[1].strip()) <= {"="} and lines[1].strip():
        body_start = 2
    body = "\n".join(lines[body_start:]).strip("\n")
    return title, body


def _insight_index_html():
    from content import render_insights_index
    entries = []
    for d in _insight_dates():
        parsed = _read_insight(d)
        if not parsed:
            continue
        title, body = parsed
        # 첫 산문 문단을 스니펫으로
        snip = ""
        for ln in body.split("\n"):
            s = ln.strip()
            if s and not s.startswith(("-", "#", "※", "(")) and ord(s[0]) < 0x1F000:
                snip = s
                break
        entries.append({"date": d, "title": title, "snippet": snip[:90]})
    return render_insights_index(entries, f"{BASE_URL}/insights")


def _insight_article_html(date_str):
    """개별 아티클 전체 HTML(SSR·SPA 공용). 없으면 None."""
    from content import render_insight
    if not _DATE_RE.match(date_str):
        return None
    parsed = _read_insight(date_str)
    if not parsed:
        return None
    title, body = parsed
    dates = _insight_dates()  # 최신순
    idx = dates.index(date_str) if date_str in dates else -1
    # 최신순 리스트라 '다음(더 이전 날짜)'은 idx+1, '이전(더 최근 날짜)'은 idx-1
    newer = dates[idx - 1] if idx > 0 else None
    older = dates[idx + 1] if 0 <= idx < len(dates) - 1 else None
    return render_insight(date_str, title, body, prev_key=older, next_key=newer,
                          canonical=f"{BASE_URL}/insights/{date_str}")


@app.get("/insights", response_class=HTMLResponse)
def insights_index():
    return _insight_index_html()


@app.get("/api/insights")
def api_insights():
    """SPA 인라인 표시용 — /insights의 <body>만. 리포트/용어해설과 같은 주입 패턴."""
    return {"html": _extract_body(_insight_index_html())}


@app.get("/insights/{date_str}", response_class=HTMLResponse)
def insight_article(date_str: str):
    html = _insight_article_html(date_str)
    if html is None:
        raise HTTPException(404, "글 없음")
    return html


@app.get("/api/insights/{date_str}")
def api_insight_article(date_str: str):
    html = _insight_article_html(date_str)
    if html is None:
        raise HTTPException(404, "글 없음")
    return {"html": _extract_body(html)}


def _compare_pairs():
    """업종 내 시총 상위 종목끼리 자동 페어링 — 수작업 큐레이션 없이 sitemap/색인용
    '엄선된 라이벌 쌍' 목록을 만든다. /compare/{code1}/{code2} 자체는 이 목록과 무관하게
    아무 종목 조합이나 받는 범용 라우트라, 검색으로 고른 조합도 항상 렌더링된다."""
    rk = get_ranking()
    by_sector = {}
    for r in rk:
        by_sector.setdefault(r.get("sector") or "기타", []).append(r)
    pairs = []
    for items in by_sector.values():
        top = sorted(items, key=lambda r: r["marcap"], reverse=True)[:4]
        if len(top) >= 2:
            pairs.append((top[0], top[1]))
        if len(top) >= 3:
            pairs.append((top[0], top[2]))
    return pairs


def _compare_html(code1, code2):
    from content import render_compare_page
    if code1 == code2:
        return None
    rk = get_ranking()
    a = next((r for r in rk if r["code"] == code1), None)
    b = next((r for r in rk if r["code"] == code2), None)
    if not a or not b:
        return None
    return render_compare_page(a, b, f"{BASE_URL}/compare/{code1}/{code2}")


@app.get("/compare", response_class=HTMLResponse)
def compare_index():
    from content import render_compare_index
    return render_compare_index(_compare_pairs(), f"{BASE_URL}/compare")


@app.get("/api/compare")
def api_compare_index():
    from content import render_compare_index
    html = render_compare_index(_compare_pairs(), f"{BASE_URL}/compare")
    return {"html": _extract_body(html)}


@app.get("/compare/{code1}/{code2}", response_class=HTMLResponse)
def compare_page(code1: str, code2: str):
    html = _compare_html(code1, code2)
    if html is None:
        raise HTTPException(404, "비교할 수 없는 종목 조합입니다")
    return html


@app.get("/api/compare/{code1}/{code2}")
def api_compare_page(code1: str, code2: str):
    html = _compare_html(code1, code2)
    if html is None:
        raise HTTPException(404, "비교할 수 없는 종목 조합입니다")
    return {"html": _extract_body(html)}


@app.get("/backtest", response_class=HTMLResponse)
def backtest_methodology():
    from content import render_backtest_methodology
    return render_backtest_methodology(f"{BASE_URL}/backtest")


@app.get("/api/backtest-methodology")
def api_backtest_methodology():
    from content import render_backtest_methodology
    html = render_backtest_methodology(f"{BASE_URL}/backtest")
    return {"html": _extract_body(html)}


def _sector_quarterly_perf():
    """섹터(17개 대분류)별 최근 분기(약 63거래일=3개월) 동일가중 수익률 — 시총상위
    10종목 기준. factor/themes.py::_perf_context와 같은 계산(21/63거래일 전 종가 대비)을
    테마가 아니라 섹터 단위로 재사용(그쪽은 네이버 테마 태그가 있는 종목만 커버해서
    전 종목을 도는 이 용도엔 안 맞음). data/sector_rotation.json(연도별 백테스트,
    2018~)과 짝지어, '역대 패턴 + 이번 분기 현재 스냅샷'을 같이 보여주는 용도."""
    rk = get_ranking()
    marcap_by_code = {r["code"]: r["marcap"] for r in rk}
    by_sector = {}
    for r in rk:
        by_sector.setdefault(r.get("sector") or "기타", []).append(r["code"])
    conn = _conn()
    out = []
    for sector, codes in by_sector.items():
        top_codes = sorted(codes, key=lambda c: marcap_by_code.get(c, 0), reverse=True)[:10]
        rets_1m, rets_3m = [], []
        for c in top_codes:
            rows = conn.execute(
                "SELECT close FROM daily_prices WHERE code=? AND close IS NOT NULL "
                "ORDER BY date DESC LIMIT 64", (c,)).fetchall()
            cl = [x[0] for x in rows]
            if len(cl) >= 22 and cl[21]:
                rets_1m.append(cl[0] / cl[21] - 1)
            if len(cl) >= 64 and cl[63]:
                rets_3m.append(cl[0] / cl[63] - 1)
        out.append({
            "sector": sector, "count": len(codes),
            "ret_1m": round(sum(rets_1m) / len(rets_1m) * 100, 1) if rets_1m else None,
            "ret_3m": round(sum(rets_3m) / len(rets_3m) * 100, 1) if rets_3m else None,
        })
    conn.close()
    out.sort(key=lambda x: (x["ret_3m"] is not None, x["ret_3m"]), reverse=True)
    return out


def _sector_rotation_history():
    import json
    path = os.path.join(os.path.dirname(__file__), "data", "sector_rotation.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/sector-rotation-review", response_class=HTMLResponse)
def sector_rotation_review():
    from content import render_sector_rotation_review
    return render_sector_rotation_review(_sector_quarterly_perf(), _sector_rotation_history(),
                                         f"{BASE_URL}/sector-rotation-review")


@app.get("/api/sector-rotation-review")
def api_sector_rotation_review():
    from content import render_sector_rotation_review
    html = render_sector_rotation_review(_sector_quarterly_perf(), _sector_rotation_history(),
                                         f"{BASE_URL}/sector-rotation-review")
    return {"html": _extract_body(html)}


@app.get("/themes-index", response_class=HTMLResponse)
def themes_index():
    from content import layout
    tmap = get_tmap()
    perf = _theme_perf_map()
    items = sorted(tmap["themes"].items(),
                   key=lambda kv: perf.get(kv[0], {}).get("ret_1m") if perf.get(kv[0], {}).get("ret_1m") is not None else -999,
                   reverse=True)
    lis = ""
    for no, t in items:
        p = perf.get(no, {})
        r1 = p.get("ret_1m")
        tag = "" if r1 is None else f' <span class="muted">({r1:+.1f}%/1M)</span>'
        lis += f'<li><a href="/t/{no}">{t["name"]}</a> <span class="muted">{len(t["codes"])}종목</span>{tag}</li>'
    from content import _ic
    body = (f'<h1>{_ic("list")} 테마별 관련주 전체 ({len(items)}개)</h1>'
            f'<p class="muted">테마를 누르면 해당 테마의 저평가·우량 종목 랭킹을 볼 수 있습니다. '
            f'수익률이 가장 강했던 테마 순으로 정렬했습니다. 매매 추천이 아닙니다.</p>'
            f'<ul style="columns:2;line-height:2;font-size:14px">{lis}</ul>'
            f'<p class="muted footnote">테마 분류: 공개 테마 데이터 참고. 정렬·분석은 자체 팩터 모델.</p>')
    return layout("한국주식 테마 전체 목록 — 관련주 가치·퀄리티 분석",
                  "266개 시장 테마별 관련주를 가치+퀄리티 팩터로 분석한 목록.",
                  f"{BASE_URL}/themes-index", body, show_subscribe=False)


def _extract_body(html: str) -> str:
    """전체 HTML 문서에서 <body> 내용만 추출(SPA 인라인 표시용 공용 헬퍼).
    뉴스레터 구독 폼은 SPA 쉘(static/index.html) 자체 풋터에 이미 있어서, 여기
    포함시키면 SPA 안에서 리포트/용어해설 등을 열 때 폼이 두 번 뜨는 중복이
    생긴다 - content.py의 <!--newsletter-block--> 마커 구간을 통째로 제거한다."""
    import re
    m = re.search(r"<body>(.*)</body>", html, re.S)
    body = m.group(1) if m else html
    return re.sub(r"<!--newsletter-block-->.*?<!--/newsletter-block-->", "", body, flags=re.S)


@app.get("/api/about")
def api_about():
    """about.html의 <body> 내용만 추출(SPA 인라인 표시용)."""
    return {"html": _extract_body(_page("about.html"))}


def _learn_compare(term):
    if not term.get("metric"):
        return []
    from glossary import COMPARE_PAIR
    rk = {r["code"]: r for r in get_ranking()}
    compare = []
    for code, fallback in COMPARE_PAIR:
        r = rk.get(code)
        compare.append({
            "code": code, "name": r["name"] if r else fallback,
            "value": (r or {}).get(term["metric"]),
            "score": (r or {}).get("score"),
        })
    return compare


@app.get("/api/learn")
def api_learn_index():
    from glossary import render_learn_index
    return {"html": _extract_body(render_learn_index(f"{BASE_URL}/learn"))}


@app.get("/api/learn/{slug}")
def api_learn_term(slug: str):
    from glossary import TERMS, render_glossary
    if slug not in TERMS:
        raise HTTPException(404, "문서 없음")
    compare = _learn_compare(TERMS[slug])
    html = render_glossary(slug, compare, f"{BASE_URL}/learn/{slug}")
    return {"html": _extract_body(html)}


@app.post("/api/newsletter/subscribe")
def newsletter_subscribe(email: str = Body(..., embed=True)):
    """이메일 뉴스레터 구독. 이메일 자체는 우리 DB(git 커밋되는 배포 DB)에 저장하지
    않고 Resend Audience API로 바로 전달 — 개인정보를 git 이력에 남기지 않기 위함."""
    email = (email or "").strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "올바른 이메일 주소를 입력해주세요.")
    api_key = os.getenv("RESEND_API_KEY")
    audience_id = os.getenv("RESEND_AUDIENCE_ID")
    if not api_key or not audience_id:
        raise HTTPException(503, "뉴스레터 기능을 준비 중입니다. 곧 열릴게요!")
    try:
        r = requests.post(
            f"https://api.resend.com/audiences/{audience_id}/contacts",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"email": email, "unsubscribed": False}, timeout=10)
    except requests.RequestException:
        raise HTTPException(502, "구독 처리 중 오류가 발생했어요. 잠시 후 다시 시도해주세요.")
    if r.status_code >= 400 and r.status_code != 409:
        raise HTTPException(502, "구독 처리 중 오류가 발생했어요. 잠시 후 다시 시도해주세요.")
    return {"ok": True}


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n"


@app.get("/ads.txt", response_class=PlainTextResponse)
def ads_txt():
    return "google.com, pub-2115777789192453, DIRECT, f08c47fec0942fa0\n"


@app.get("/favicon.ico")
def favicon():
    # <link rel=icon>은 있지만 루트 /favicon.ico를 직접 찾는 크롤러·구형 클라이언트용.
    return RedirectResponse("/static/favicon-32.png", status_code=301)


@app.get("/sitemap.xml")
def sitemap():
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    from glossary import TERMS
    from factor.sectors import SLUGS
    urls = [("/", "daily", "1.0"), ("/insights", "daily", "0.9"),
            ("/weekly", "weekly", "0.9"),
            ("/anomaly-report", "weekly", "0.8"), ("/learn", "monthly", "0.8"),
            ("/sector-report", "monthly", "0.8"), ("/monthly", "monthly", "0.8"),
            ("/earnings-report", "daily", "0.8"), ("/compare", "weekly", "0.7"),
            ("/themes-index", "weekly", "0.7"), ("/about", "monthly", "0.5"),
            ("/backtest", "monthly", "0.8"), ("/sector-rotation-review", "weekly", "0.8")]
    urls += [(f"/insights/{d}", "monthly", "0.8") for d in _insight_dates()]
    urls += [(f"/learn/{slug}", "monthly", "0.7") for slug in TERMS]
    urls += [(f"/sector-report/{slug}", "monthly", "0.7") for slug in SLUGS.values()]
    # /compare/{code1}/{code2}는 어떤 조합이든 렌더링되는 범용 라우트지만(검색으로 고른
    # 조합도 항상 동작), sitemap엔 업종+시총 기반 자동 큐레이션 쌍만 노출한다(전체 조합은
    # 수십만 개라 sitemap에 다 넣는 게 오히려 스팸성으로 보일 수 있음).
    urls += [(f"/compare/{a['code']}/{b['code']}", "monthly", "0.7") for a, b in _compare_pairs()]
    parts = [f"<url><loc>{BASE_URL}{p}</loc><lastmod>{today}</lastmod>"
             f"<changefreq>{cf}</changefreq><priority>{pr}</priority></url>"
             for p, cf, pr in urls]
    # 테마 페이지(/t/{no}, ~250개)는 sitemap에서 제외 — 대부분 "구성종목 N개 중 N개 분석,
    # 최근 1개월 수익률 X%" 식으로 사실상 동일 템플릿에 숫자만 바뀌는 얇은 콘텐츠라(애드센스
    # "부가가치 없는 자동생성 콘텐츠" 지적과 맞물림), content.py::render_theme_page에서도
    # noindex,follow를 짝지어 붙였다. 페이지 자체는 그대로 열람 가능(사용자 기능 무손실).
    # 개별 종목 페이지(/s/{code}) — 실제 검색어("삼성전자 PER" 등)에 대응하는 SSR
    # 랜딩페이지라 색인 가치가 큼. 다만 재무 연혁이 MIN_FIN_YEARS_FOR_INDEX 미만인
    # 신규 소형주(전종목 확장으로 늘어난 1개년치 종목들)는 얇은 페이지라 제외한다
    # (stock_page() 라우트의 noindex 처리와 동일 기준 — 위 테마페이지와 같은 패턴).
    conn = _conn()
    fin_year_counts = dict(conn.execute(
        "SELECT code, COUNT(*) FROM financials GROUP BY code").fetchall())
    conn.close()
    for r in get_ranking():
        if not _stock_index_worthy(fin_year_counts.get(r["code"], 0)):
            continue
        parts.append(f"<url><loc>{BASE_URL}/s/{r['code']}</loc><lastmod>{today}</lastmod>"
                     f"<changefreq>daily</changefreq><priority>0.7</priority></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           + "".join(parts) + "</urlset>")
    return Response(content=xml, media_type="application/xml")


def _r(v, nd=1):
    if v is None:
        return None
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None
