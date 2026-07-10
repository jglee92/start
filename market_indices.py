# -*- coding: utf-8 -*-
"""주요 시장지수(코스피/코스닥/나스닥/S&P500/국제 금) 현재가 - 홈 화면 표시 전용.
Yahoo Finance 비공식 차트 API 사용(yfinance 라이브러리가 내부적으로 쓰는 것과 동일
엔드포인트, 키 불필요). KOSPI/KOSDAQ은 개장중, 미국/금은 각자 현지 장 시간에만
활발히 갱신되고 그 외 시간엔 마지막 값을 그대로 반환한다."""
from __future__ import annotations
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

INDICES = [
    {"key": "kospi", "name": "코스피", "symbol": "^KS11"},
    {"key": "kosdaq", "name": "코스닥", "symbol": "^KQ11"},
    {"key": "nasdaq", "name": "나스닥", "symbol": "^IXIC"},
    {"key": "sp500", "name": "S&P 500", "symbol": "^GSPC"},
    {"key": "dji", "name": "다우존스", "symbol": "^DJI"},
    {"key": "nikkei", "name": "니케이225", "symbol": "^N225"},
    {"key": "shanghai", "name": "상해종합", "symbol": "000001.SS"},
    {"key": "gold", "name": "국제 금", "symbol": "GC=F"},
    {"key": "usdkrw", "name": "원/달러", "symbol": "KRW=X"},
    {"key": "wti", "name": "WTI유가", "symbol": "CL=F"},
]
INDEX_BY_KEY = {ix["key"]: ix for ix in INDICES}


def _fetch_one(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        r.raise_for_status()
        meta = r.json()["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price is None or not prev:
            return None
        return {
            "price": round(price, 2),
            "prev_close": round(prev, 2),
            "chg_pct": round((price / prev - 1) * 100, 2),
            "currency": meta.get("currency"),
        }
    except Exception:
        return None


def fetch_indices():
    out = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(_fetch_one, ix["symbol"]): ix for ix in INDICES}
        for fut in as_completed(futs):
            ix = futs[fut]
            data = fut.result()
            if data:
                out[ix["key"]] = {"name": ix["name"], **data}
    return out


_RANGE_INTERVAL = {"1mo": "1d", "6mo": "1d", "1y": "1wk"}


def fetch_history(key, range_="6mo"):
    """지수 클릭시 차트용 히스토리(날짜,종가). range: 1mo/6mo/1y."""
    ix = INDEX_BY_KEY.get(key)
    if not ix:
        return None
    interval = _RANGE_INTERVAL.get(range_, "1d")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ix['symbol'])}"
           f"?range={range_}&interval={interval}")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    r.raise_for_status()
    result = r.json()["chart"]["result"][0]
    ts = result.get("timestamp") or []
    closes = result["indicators"]["quote"][0].get("close") or []
    points = [{"t": t, "c": round(c, 4)} for t, c in zip(ts, closes) if c is not None]
    return {"key": key, "name": ix["name"], "points": points}
