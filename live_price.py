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
    """실제 정규장 시간(09:00~15:30). 표시용 '장중' 배지 등에 쓸 엄격한 정의."""
    now = (now or datetime.now(KST)).astimezone(KST)
    if now.weekday() >= 5:   # 토(5)/일(6)
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 <= t <= 15 * 60 + 30


def should_refresh_live(now=None) -> bool:
    """실시간가 갱신을 '시도'할지 여부. 09:00~19:00로 정규장(15:30 마감)보다 넓게 잡음 —
    장마감 후~저녁 정식 daily_prices 갱신(19:00) 사이에 공백이 생기면 daily_prices가
    하루 이상 stale한 상태로 노출되는 문제가 있었음(실제 발생). 이 구간엔 네이버가
    당일 종가를 그대로 반환해주므로(장중이 아니라도 마지막 체결가 조회는 됨) 계속
    갱신 시도하는 게 더 정확하다."""
    now = (now or datetime.now(KST)).astimezone(KST)
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 <= t <= 19 * 60


def _fetch_one(code: str, timeout=6):
    try:
        r = requests.get(_URL.format(code=code), headers=H, timeout=timeout)
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
        # tradeStopType.code: "1"=정상거래, "2"=거래정지 — 같은 응답에서 공짜로 얻어짐
        # (별도 호출 불필요). 코드가 없거나 "1"이 아니면 정지로 간주.
        tst = d.get("tradeStopType") or {}
        halted = tst.get("code") not in (None, "1")
        return {
            "price": price_f,
            "chg_pct": float(pct) if pct is not None else None,
            "prev_close": prev_close,
            "halted": halted,
        }
    except Exception:
        return None


def fetch_many(codes, workers: int = 10, timeout=6):
    """codes -> {code: {"price":, "chg_pct":, "halted":}} (실패한 종목은 결과에서 제외).

    실제 사고: Render 배포환경→네이버 API 개별 요청이 로컬보다 훨씬 느려서(또는
    상당수가 타임아웃까지 감), 전종목(~2,456개) 스캔이 이론상 최악치(2456/20*6초
    ≈12분)를 넘겨 15분 넘게 안 끝나는 문제가 실제 발생. per-요청 timeout을 호출부
    (fetch_halted_set)에서 짧게 넘겨 최악의 경우도 확 줄인다."""
    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {c: ex.submit(_fetch_one, c, timeout) for c in codes}
        for c, fut in futs.items():
            try:
                r = fut.result(timeout=timeout + 2)
            except Exception:
                r = None
            if r:
                out[c] = r
    return out


def fetch_halted_set(codes, workers: int = 40, timeout=2.5):
    """codes 중 현재 거래정지 상태인 코드 집합. 전체 유니버스처럼 넓은 대상을
    스캔할 때 쓰는 용도라 가격표시용 fetch_many보다 병렬도는 높이고 개별
    타임아웃은 짧게(2.5초) — 거래정지는 30분 캐시라 가끔 느린 응답 하나 놓쳐도
    다음 스캔에서 다시 잡히므로, 정확도보다 전체 완료 시간을 짧게 잡는 게 안전."""
    return {c for c, info in fetch_many(codes, workers=workers, timeout=timeout).items()
            if info.get("halted")}
