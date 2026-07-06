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


@app.get("/api/ranking")
def api_ranking():
    rk = get_ranking()
    asof = rk[0]["price_date"] if rk else None
    slim = [{
        "rank": r["rank"], "code": r["code"], "name": r["name"],
        "market": r["market"], "sector": r.get("sector"), "score": r["score"],
        "per": _r(r["per"]), "pbr": _r(r["pbr"], 2), "psr": _r(r["psr"], 2),
        "roe": _r(r["roe"]), "op_margin": _r(r["op_margin"]),
        "debt_ratio": _r(r["debt_ratio"], 0),
        "marcap_eok": round(r["marcap"] / 1e8),
        "fiscal_year": r["fiscal_year"],
        "price": r.get("price"), "chg_pct": _r(r.get("chg_pct"), 2),
        "revenue_eok": round(r["revenue"] / 1e8) if r.get("revenue") else None,
        "op_profit_eok": round(r["op_profit"] / 1e8) if r.get("op_profit") else None,
        "div_yield": _r(r.get("div_yield"), 2),
        "rev_growth": _r(r.get("rev_growth")),
        "dims": r.get("dims"),
    } for r in rk]
    return {"asof": asof, "count": len(slim), "rows": slim}


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
    conn.close()
    if row is None and not fins:
        raise HTTPException(404, "종목 없음")
    name = row["name"] if row else code
    themes = get_tmap().get("stock_themes", {}).get(code, [])
    return {
        "code": code, "name": name, "themes": themes,
        "summary": None if row is None else {
            "rank": row["rank"], "score": row["score"], "market": row["market"],
            "price": row["price"], "marcap_eok": round(row["marcap"] / 1e8),
            "per": _r(row["per"]), "pbr": _r(row["pbr"], 2),
            "psr": _r(row["psr"], 2), "roe": _r(row["roe"]),
            "op_margin": _r(row["op_margin"]), "debt_ratio": _r(row["debt_ratio"], 0),
            "div_yield": _r(row.get("div_yield"), 2), "rev_growth": _r(row.get("rev_growth")),
            "breakdown": row["breakdown"], "dims": row.get("dims"),
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


@app.get("/api/theme/{name}")
def api_theme(name: str):
    """테마 구성종목(현재 랭킹 데이터 결합) + 상위 종목 뉴스 통합."""
    tmap = get_tmap()
    theme = next((t for t in tmap["themes"].values() if t["name"] == name), None)
    if not theme:
        raise HTTPException(404, "테마 없음")
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
    merged = []
    for s in stocks[:3]:
        for it in _google_news(f"{s['name']} 주식", keep_ts=True)[:5]:
            it["stock"] = s["name"]
            merged.append(it)
    seen, news = set(), []
    for it in sorted(merged, key=lambda x: x.get("_ts", 0), reverse=True):
        if it["title"] in seen:
            continue
        seen.add(it["title"])
        news.append({k: v for k, v in it.items() if k != "_ts"})
    return {"theme": name, "count": len(stocks), "stocks": stocks, "news": news[:12]}


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
    rk = get_ranking()
    return {"ok": True, "count": len(rk), "asof": rk[0]["price_date"] if rk else None}


_news_cache = {}   # query -> (ts, items)


def _google_news(query: str, keep_ts: bool = False):
    """구글뉴스 RSS(키 불필요). 30분 캐시. 최근순 정렬된 items 반환."""
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
                key = "".join((it["title"] or "").split()).lower()[:40]
                if key in seen:
                    continue
                seen.add(key)
                dedup.append(it)
            items = dedup
        except Exception:
            items = []
        _news_cache[query] = (now, items)
    if keep_ts:
        return [dict(x) for x in items]
    return [{k: v for k, v in x.items() if k != "_ts"} for x in items]


@app.get("/api/news/{code}")
def api_news(code: str):
    rk = get_ranking()
    row = next((r for r in rk if r["code"] == code), None)
    name = row["name"] if row else code
    return {"code": code, "name": name, "items": _google_news(f"{name} 주식")[:10]}


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
        for it in _google_news(f"{s['name']} 주식", keep_ts=True)[:5]:
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
        "AND date>=? ORDER BY date", (code, "2025-01-01")).fetchall()
    conn.close()
    name = row["name"] if row else _name_of(code)
    if row is None and not fins:
        raise HTTPException(404, "종목 없음")
    summary = None if row is None else {
        "score": row["score"], "per": _r(row["per"]), "pbr": _r(row["pbr"], 2),
        "roe": _r(row["roe"]), "op_margin": _r(row["op_margin"]),
        "debt_ratio": _r(row["debt_ratio"], 0), "marcap_eok": round(row["marcap"] / 1e8),
        "dims": row.get("dims")}
    financials = [{"year": f[0], "revenue": f[1], "op_profit": f[2],
                   "net_income": f[3], "equity": f[4], "debt_ratio": _r(f[6], 0),
                   "op_margin": _r(f[7])} for f in fins]
    prices_l = [{"date": p[0], "close": p[1]} for p in prices[::2]]
    themes = get_tmap().get("stock_themes", {}).get(code, [])
    news = _google_news(f"{name} 주식")[:10]
    return render_stock_page(code, name, summary, financials, prices_l, news,
                             themes, f"{BASE_URL}/s/{code}")


@app.get("/weekly", response_class=HTMLResponse)
def weekly():
    from content import render_weekly
    perf = [t for t in _theme_perf_map().values() if t["priced"] >= 5
            and t["ret_1m"] is not None]
    perf.sort(key=lambda t: t["ret_1m"], reverse=True)
    strong, weak = perf[:10], perf[-5:][::-1]
    rk = get_ranking()
    asof = rk[0]["price_date"] if rk else ""
    top_value = [{"code": r["code"], "name": r["name"], "score": r["score"],
                  "per": _r(r["per"]), "pbr": _r(r["pbr"], 2), "roe": _r(r["roe"]),
                  "sector": r.get("sector")} for r in rk[:15]]
    return render_weekly(strong, weak, top_value, asof, f"{BASE_URL}/weekly")


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


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n"


@app.get("/sitemap.xml")
def sitemap():
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    urls = [("/", "daily", "1.0"), ("/weekly", "weekly", "0.9"),
            ("/themes-index", "weekly", "0.7"), ("/about", "monthly", "0.5")]
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
