# -*- coding: utf-8 -*-
"""
장중 '현재가' 캐시. daily_prices(백테스트용 정식 종가, 하루 1회 갱신)와는 완전히 분리된
화면표시 전용 캐시 — 절대 daily_prices에 쓰지 않는다(백테스트 데이터 신뢰성 보호).

네이버 금융 실시간 폴링 엔드포인트를 개인 리서치용으로 정중하게 사용(캐시 TTL로 과호출 방지).
장 마감 후에는 그날의 마지막 값이 그대로 남아 자연스럽게 '오늘자 종가 근사치' 역할을 한다 —
저녁 정식 일봉 작업이 daily_prices를 갱신하면 다음날부터는 그 값이 기준이 된다.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_URL = "https://polling.finance.naver.com/api/realtime/domestic/stock/{code}"
KST = timezone(timedelta(hours=9))

TTL_SECONDS = 300   # 5분 — 이보다 오래되면 다음 요청에서 갱신 트리거


def is_market_hours(now=None) -> bool:
    now = (now or datetime.now(KST)).astimezone(KST)
    if now.weekday() >= 5:   # 토(5)/일(6)
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 <= t <= 15 * 60 + 30


def _fetch_one(code: str):
    try:
        r = requests.get(_URL.format(code=code), headers=H, timeout=6)
        js = r.json()
        d = (js.get("datas") or [None])[0]
        if not d:
            return None
        price = d.get("closePrice")
        pct = d.get("fluctuationsRatio")
        diff = d.get("compareToPreviousClosePrice")
        if price is None:
            return None
        price_f = float(str(price).replace(",", ""))
        prev_close = None
        if diff is not None:
            try:
                prev_close = price_f - float(str(diff).replace(",", ""))
            except ValueError:
                prev_close = None
        return {
            "price": price_f,
            "chg_pct": float(pct) if pct is not None else None,
            "prev_close": prev_close,
        }
    except Exception:
        return None


def fetch_many(codes, workers: int = 10):
    """codes -> {code: {"price":, "chg_pct":}} (실패한 종목은 결과에서 제외)."""
    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {c: ex.submit(_fetch_one, c) for c in codes}
        for c, fut in futs.items():
            try:
                r = fut.result(timeout=10)
            except Exception:
                r = None
            if r:
                out[c] = r
    return out
