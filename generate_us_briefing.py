# -*- coding: utf-8 -*-
"""'간밤 미국증시 & 경제 뉴스 정리' 일일 드래프트 생성 — 네이버 블로그 등에 매일
쌓는 정리글. 사용자가 본 블로그(미국주식/경제 정리)류를 우리 데이터로 반자동화.

근거(사실)만 사용: (1) app._overnight_us_indices() 나스닥·S&P500·원달러 종가·등락,
(2) app._google_news()로 모은 미국증시·경제 뉴스 헤드라인. Claude(haiku)가 이 둘만
근거로 사실 위주 정리글을 쓴다 — 예측·매수매도·목표가 금지(정직 브랜드 유지).

미국장 마감은 KST 05~06시라 이 스크립트는 마감 후(07시경) 워크플로우로 돌려 종가를
반영한다. 출력: content_out/<date>/us_briefing.txt (제목 첫 줄 + 본문, 네이버 붙여넣기용).
필요: ANTHROPIC_API_KEY.
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timezone, timedelta

import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import app as A

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"
KST = timezone(timedelta(hours=9))

_SYSTEM = """당신은 한국 개인투자자를 위한 '머니체크업'의 시장 정리 필자입니다. 주어진
'간밤 미국증시 지수 수치'와 '뉴스 헤드라인'만 근거로, 사실 위주의 아침 정리글을 씁니다.

엄격한 규칙:
- 주어진 숫자·헤드라인에 있는 사실만 쓰세요. 없는 수치·전망·목표가를 지어내지 마세요.
- 예측·매수/매도 추천 금지("오를 것", "지금이 기회" 같은 표현 금지). 낚시·과장 금지.
- 헤드라인은 사실만 담백하게 요약(원문 왜곡 금지).
- 한국어. 아래 구조를 정확히 지키세요:

제목: (그날 핵심을 담은 담백한 한 줄. 물음표 낚시 금지)

■ 간밤 미국증시
- 나스닥·S&P500·원달러 수치와 방향을 한 줄씩

■ 주요 뉴스 정리
- 헤드라인 3~6개를 각각 한 줄로 사실 요약

■ 국내장 참고
- 위 사실들이 국내 투자자에게 주는 배경을 사실 위주로 2~3문장(예측 아님)

※ 이 글은 공개 데이터·뉴스를 정리한 정보 제공용이며, 매수·매도 추천이 아닙니다.

추천 태그:
#미국증시 #나스닥 #경제뉴스 #환율 #머니체크업 (주제에 맞게 6~8개)"""


def _indices_text():
    ix = A._overnight_us_indices()
    if not ix:
        return None
    lines = []
    for key, label in (("nasdaq", "나스닥"), ("sp500", "S&P500")):
        d = ix.get(key)
        if d and d.get("chg_pct") is not None:
            px = f"{d['price']:,.2f} " if d.get("price") else ""
            lines.append(f"{label}: {px}({d['chg_pct']:+.2f}%)")
    usd = ix.get("usdkrw")
    if usd and usd.get("price"):
        chg = f" ({usd['chg_pct']:+.2f}%)" if usd.get("chg_pct") is not None else ""
        lines.append(f"원달러: {usd['price']:,.1f}원{chg}")
    return "\n".join(lines) if lines else None


def _headlines():
    seen, out = set(), []
    for q in ("미국 증시 나스닥", "연준 금리 환율", "미국 경제 지표"):
        try:
            for n in A._google_news(q)[:5]:
                t = (n.get("title") or "").strip()
                if t and t not in seen:
                    seen.add(t)
                    src = n.get("source") or ""
                    out.append(f"- {t}" + (f" ({src})" if src else ""))
        except Exception:
            pass
        if len(out) >= 8:
            break
    return "\n".join(out[:8])


def _call_claude(payload, api_key):
    import claude_status
    body = {"model": MODEL, "max_tokens": 2000, "system": _SYSTEM,
            "messages": [{"role": "user", "content": payload}]}
    r = requests.post(API_URL, headers={
        "x-api-key": api_key, "anthropic-version": "2023-06-01",
        "content-type": "application/json"}, json=body, timeout=120)
    if r.status_code != 200:
        claude_status.record_result("generate_us_briefing", False,
                                    status_code=r.status_code, response_text=r.text)
        raise RuntimeError(f"Claude API 오류 {r.status_code}: {r.text[:200]}")
    text = "".join(b.get("text", "") for b in r.json().get("content", [])
                   if b.get("type") == "text").strip()
    claude_status.record_result("generate_us_briefing", bool(text))
    return text


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("::warning::ANTHROPIC_API_KEY 미설정 — 미국 정리글 생성 건너뜀.")
        return
    idx = _indices_text()
    if not idx:
        print("::warning::미국 지수 수치를 못 가져옴(야후 장애 등) — 생략.")
        return
    heads = _headlines() or "- (수집된 뉴스 헤드라인 없음)"
    today = datetime.now(KST).strftime("%Y-%m-%d")
    payload = (f"[간밤 미국증시 지수]\n{idx}\n\n[뉴스 헤드라인]\n{heads}\n\n"
               f"위 사실만 근거로 오늘({today}) 아침 정리글을 써주세요.")
    text = _call_claude(payload, api_key)
    if not text:
        print("::warning::빈 응답 — 생략.")
        return
    # 첫 줄 제목의 스캐폴딩 제거(네이버 제목칸에 바로 복사) — '제목:' 라벨과 마크다운 '#'.
    text = text.lstrip()
    for pref in ("제목:", "#", "＃"):
        while text.startswith(pref):
            text = text[len(pref):].lstrip()

    day_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "content_out", today)
    os.makedirs(day_dir, exist_ok=True)
    dst = os.path.join(day_dir, "us_briefing.txt")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")
    print(f"저장: {dst}\n---\n{text[:400]}")


if __name__ == "__main__":
    main()
