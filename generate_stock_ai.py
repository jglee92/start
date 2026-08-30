# -*- coding: utf-8 -*-
"""
종목별 AI 종합해설 생성 — 색인 대상(시총 상위) 종목에 대해 Claude로 애널리스트풍
'종합 해설' 문단을 써서 data/stock_ai_narratives.json 에 캐시한다.

- 대상: 재무연혁 MIN_FIN_YEARS 이상 중 시가총액 상위 TOP_N (= 사이트가 색인하는 종목).
- 멱등/비용절감: 종목의 입력 데이터 해시가 캐시와 같으면 건너뜀(과금 0). 재무는 분기
  단위로만 바뀌므로 대부분의 주간 실행은 대부분 스킵된다.
- 폴백: 사이트(app.py)는 이 캐시가 있으면 AI 해설을 쓰고, 없으면 템플릿
  (factor.interpret.stock_narrative)으로 자동 폴백 → API 실패/미설정이어도 안전.

주 1회 워크플로우(stock-ai-narrative.yml)로 실행. 필요: ANTHROPIC_API_KEY.
사용: python generate_stock_ai.py  (단독 실행 시 상위 종목 갱신)
"""
from __future__ import annotations
import os
import sys
import json
import time
import hashlib

import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import db
from factor.current import compute_ranking

MODEL = "claude-sonnet-5"
API_URL = "https://api.anthropic.com/v1/messages"
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "stock_ai_narratives.json")
MIN_FIN_YEARS = 3          # app.py MIN_FIN_YEARS_FOR_INDEX 와 일치
TOP_N = 40                 # app.py MAX_INDEXED_STOCKS 와 일치(색인 대상만 생성)

_SYSTEM = """당신은 한국 주식 리서치 도구 '머니체크업'의 애널리스트입니다. 주어진 한 종목의
정량 데이터(건강점수·4차원 등급·재무 추이·재무 이상신호·회계감사의견)만 근거로,
이 회사가 '지금 어떤 상태인가'를 사람이 읽는 3~5문장의 한국어 문단 하나로 요약합니다.

엄격한 규칙:
- 주어진 숫자·사실만 사용하세요. 데이터에 없는 수치나 미래 실적·주가·전망을 지어내지 마세요.
- 예측·매수/매도 추천 금지. "유망하다", "오를 것" 같은 표현을 쓰지 마세요.
- 강점과 약점을 균형 있게 서술하고, 이상신호(적자전환·부채급증·비적정 감사의견 등)가
  있으면 반드시 언급하며 원인 확인을 권합니다.
- 담백하고 신뢰감 있는 톤. 과장·홍보성 문구 금지. 줄바꿈 없이 한 문단으로.
- 문단 끝에 "(같은 업종·시총 내 상대 비교 기준)"을 덧붙입니다.
- 해설 문단 텍스트만 출력하세요(머리말·따옴표·목록 없이)."""


def _payload(r, fins):
    """Claude에 넘길 근거 데이터(사실만). fins: (year,revenue,op_profit,net_income,
    equity,liabilities,debt_ratio,op_margin) 오름차순."""
    dims = r.get("dims") or {}

    def dim(k):
        d = dims.get(k) or {}
        return {"별점": d.get("stars"), "등급": d.get("label")}

    trend = [{"연도": f[0],
              "매출_억": round(f[1] / 1e8) if f[1] is not None else None,
              "영업이익_억": round(f[2] / 1e8) if f[2] is not None else None}
             for f in fins[-4:]]
    return {
        "종목명": r["name"], "업종": r.get("sector"),
        "건강점수(100점)": r.get("score"),
        "PER": r.get("per"), "PBR": r.get("pbr"), "ROE_%": r.get("roe"),
        "영업이익률_%": r.get("op_margin"), "부채비율_%": r.get("debt_ratio"),
        "매출성장률_%": r.get("rev_growth"),
        "4차원등급(별5점)": {"밸류에이션": dim("value"), "수익성": dim("profit"),
                              "안정성": dim("safety"), "성장성": dim("growth")},
        "최근재무추이": trend,
        "재무이상신호": [f.get("label") for f in (r.get("flags") or [])],
        "회계감사의견": r.get("audit_opinion"),
    }


def _hash(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _call_claude(payload, api_key):
    import claude_status
    body = {
        "model": MODEL,
        "max_tokens": 700,
        "system": _SYSTEM,
        "messages": [{"role": "user",
                      "content": "다음 종목 데이터로 종합 해설 문단을 써주세요:\n"
                                 + json.dumps(payload, ensure_ascii=False, indent=1)}],
    }
    r = requests.post(API_URL, headers={
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }, json=body, timeout=120)
    if r.status_code != 200:
        claude_status.record_result("generate_stock_ai", False,
                                    status_code=r.status_code, response_text=r.text)
        raise RuntimeError(f"Claude API 오류 {r.status_code}: {r.text[:200]}")
    data = r.json()
    text = "".join(b.get("text", "") for b in data.get("content", [])
                   if b.get("type") == "text").strip()
    if not text:
        raise RuntimeError("빈 응답")
    return text


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("::warning::ANTHROPIC_API_KEY 미설정 — 생성 건너뜀(사이트는 템플릿 폴백).")
        return

    conn = db.connect()
    rows = compute_ranking(conn)
    fin_counts = dict(conn.execute(
        "SELECT code, COUNT(*) FROM financials GROUP BY code").fetchall())
    eligible = [r for r in rows if fin_counts.get(r["code"], 0) >= MIN_FIN_YEARS]
    eligible.sort(key=lambda r: r["marcap"], reverse=True)
    targets = eligible[:TOP_N]
    print(f"대상 {len(targets)}종목(색인 상위)")

    cache = {}
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH, encoding="utf-8") as f:
            cache = json.load(f)

    made = skipped = failed = 0
    import claude_status
    for i, r in enumerate(targets, 1):
        code = r["code"]
        fins = conn.execute(
            "SELECT year,revenue,op_profit,net_income,equity,liabilities,"
            "debt_ratio,op_margin FROM financials WHERE code=? ORDER BY year",
            (code,)).fetchall()
        payload = _payload(r, fins)
        h = _hash(payload)
        if cache.get(code, {}).get("hash") == h:
            skipped += 1
            continue
        try:
            text = _call_claude(payload, api_key)
            cache[code] = {"text": text, "hash": h, "name": r["name"]}
            made += 1
            print(f"  [{i}/{len(targets)}] {r['name']}({code}) 생성")
            time.sleep(0.6)   # 레이트리밋 여유
        except Exception as e:
            failed += 1
            print(f"  [{i}/{len(targets)}] {r['name']}({code}) 실패: {e}")

    conn.close()
    # 색인 대상에서 빠진(시총 하락 등) 종목의 오래된 캐시는 제거해 파일이 무한히 안 커지게.
    valid = {r["code"] for r in targets}
    cache = {c: v for c, v in cache.items() if c in valid}

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1, sort_keys=True)
    claude_status.record_result("generate_stock_ai", failed == 0)
    print(f"완료: 생성 {made} · 스킵(변동없음) {skipped} · 실패 {failed} · 총 {len(cache)}종목")


if __name__ == "__main__":
    main()
