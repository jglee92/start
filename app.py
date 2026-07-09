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
import time
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

import db
from factor.universe import build_master
from factor.current import compute_ranking

app = FastAPI(title="가치+퀄리티 팩터 대시보드")

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


def get_ranking():
    if _cache["ranking"] is None:
        conn = _conn()
        if _cache["master"] is None:
            _cache["master"] = build_master()
        _cache["ranking"] = compute_ranking(conn, master=_cache["master"])
        conn.close()
    return _cache["ranking"]


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
                           "sector": r.get("sector")})
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
BASE_URL = os.getenv("SITE_BASE_URL", "https://example.com").rstrip("/")
_STATIC = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


def _page(fname):
    with open(os.path.join(_STATIC, fname), encoding="utf-8") as f:
        return f.read()


@app.get("/", response_class=HTMLResponse)
def index():
    return _page("index.html")


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
                           "sector": r.get("sector")})
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
        "dims": row.get("dims"), "flags": row.get("flags") or []}
    financials = [{"year": f[0], "revenue": f[1], "op_profit": f[2],
                   "net_income": f[3], "equity": f[4], "debt_ratio": _r(f[6], 0),
                   "op_margin": _r(f[7])} for f in fins]
    prices_l = [{"date": p[0], "close": p[1]} for p in prices[::2]]
    themes = _stock_theme_pairs(code)
    news = _google_news(f"{name} 주식", stock_name=name)[:10]
    disclosures = api_disclosures(code).get("items", [])
    return render_stock_page(code, name, summary, financials, prices_l, news,
                             themes, disclosures, period_returns, f"{BASE_URL}/s/{code}",
                             audit, quarterly)


def _weekly_ctx():
    from content import render_weekly
    perf = [t for t in _theme_perf_map().values() if t["priced"] >= 5
            and t["ret_1m"] is not None]
    perf.sort(key=lambda t: t["ret_1m"], reverse=True)
    strong, weak = perf[:10], perf[-5:][::-1]
    rk = get_ranking()
    asof = get_asof()
    top_value = [{"code": r["code"], "name": r["name"], "score": r["score"],
                  "per": _r(r["per"]), "pbr": _r(r["pbr"], 2), "roe": _r(r["roe"]),
                  "sector": r.get("sector")} for r in rk[:15]]
    movers_up, movers_down = _rank_movers(rk, get_ranking_asof(7))
    return render_weekly, strong, weak, top_value, asof, movers_up, movers_down


@app.get("/weekly", response_class=HTMLResponse)
def weekly():
    render_weekly, strong, weak, top_value, asof, movers_up, movers_down = _weekly_ctx()
    return render_weekly(strong, weak, top_value, asof, f"{BASE_URL}/weekly", movers_up, movers_down)


@app.get("/api/weekly")
def api_weekly():
    render_weekly, strong, weak, top_value, asof, movers_up, movers_down = _weekly_ctx()
    html = render_weekly(strong, weak, top_value, asof, f"{BASE_URL}/weekly", movers_up, movers_down)
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
    return render_sector_index(f"{BASE_URL}/sector-report")


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
    return {"html": _extract_body(render_sector_index(f"{BASE_URL}/sector-report"))}


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
                "code": r["code"], "name": r["name"],
                "text": f["text"], "emoji": f["emoji"]})
    return render_anomaly_report(grouped, asof, f"{BASE_URL}/anomaly-report")


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


@app.get("/earnings-report", response_class=HTMLResponse)
def earnings_report():
    from content import render_earnings_report
    return render_earnings_report(_earnings_items(), f"{BASE_URL}/earnings-report")


@app.get("/api/earnings-report")
def api_earnings_report():
    from content import render_earnings_report
    html = render_earnings_report(_earnings_items(), f"{BASE_URL}/earnings-report")
    return {"html": _extract_body(html)}


@app.get("/themes-index", response_class=HTMLResponse)
def themes_index():
    from content import layout
    tmap = get_tmap()
    perf = _theme_perf_map()
    items = sorted(tmap["themes"].items(),
                   key=lambda kv: len(kv[1]["codes"]), reverse=True)
    lis = ""
    for no, t in items:
        p = perf.get(no, {})
        r1 = p.get("ret_1m")
        tag = "" if r1 is None else f' <span class="muted">({r1:+.1f}%/1M)</span>'
        lis += f'<li><a href="/t/{no}">{t["name"]}</a> <span class="muted">{len(t["codes"])}종목</span>{tag}</li>'
    body = (f'<h1>테마별 관련주 전체 ({len(items)}개)</h1>'
            f'<p class="muted">각 테마를 가치+퀄리티 팩터로 분석한 페이지입니다.</p>'
            f'<ul style="columns:2;line-height:2;font-size:14px">{lis}</ul>')
    return layout("한국주식 테마 전체 목록 — 관련주 가치·퀄리티 분석",
                  "266개 시장 테마별 관련주를 가치+퀄리티 팩터로 분석한 목록.",
                  f"{BASE_URL}/themes-index", body)


def _extract_body(html: str) -> str:
    """전체 HTML 문서에서 <body> 내용만 추출(SPA 인라인 표시용 공용 헬퍼)."""
    import re
    m = re.search(r"<body>(.*)</body>", html, re.S)
    return m.group(1) if m else html


@app.get("/api/about")
def api_about():
    """about.html의 <body> 내용만 추출(SPA 인라인 표시용)."""
    return {"html": _extract_body(_page("about.html"))}


def _learn_compare(term):
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


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n"


@app.get("/sitemap.xml")
def sitemap():
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    from glossary import TERMS
    from factor.sectors import SLUGS
    urls = [("/", "daily", "1.0"), ("/weekly", "weekly", "0.9"),
            ("/anomaly-report", "weekly", "0.8"), ("/learn", "monthly", "0.8"),
            ("/sector-report", "monthly", "0.8"), ("/monthly", "monthly", "0.8"),
            ("/earnings-report", "daily", "0.8"),
            ("/themes-index", "weekly", "0.7"), ("/about", "monthly", "0.5")]
    urls += [(f"/learn/{slug}", "monthly", "0.7") for slug in TERMS]
    urls += [(f"/sector-report/{slug}", "monthly", "0.7") for slug in SLUGS.values()]
    parts = [f"<url><loc>{BASE_URL}{p}</loc><lastmod>{today}</lastmod>"
             f"<changefreq>{cf}</changefreq><priority>{pr}</priority></url>"
             for p, cf, pr in urls]
    for no in get_tmap().get("themes", {}):
        parts.append(f"<url><loc>{BASE_URL}/t/{no}</loc><lastmod>{today}</lastmod>"
                     f"<changefreq>weekly</changefreq><priority>0.6</priority></url>")
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
