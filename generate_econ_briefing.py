# -*- coding: utf-8 -*-
"""'오늘의 경제 뉴스 정리' 일일 드래프트 — 네이버 뉴스 검색 API로 경제 뉴스를 모아
Claude(haiku)가 사실 위주로 하루치 정리글을 쓴다. 네이버 블로그 등에 매일 쌓는 용도.

근거는 '네이버 뉴스 헤드라인+요약 스니펫'만. 예측·매수매도·낚시 금지(정직 브랜드).
출력: content_out/<date>/econ_briefing.txt (제목 첫 줄 + 본문, 붙여넣기용).
필요: NAVER_CLIENT_ID/SECRET(naver_news) + ANTHROPIC_API_KEY. 둘 중 하나라도 없으면 스킵.
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

import naver_news

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"
KST = timezone(timedelta(hours=9))

# 경제 뉴스 검색 주제(중복 제거해 상위 헤드라인만 요약 근거로 사용)
QUERIES = ["한국 경제", "금리 환율", "코스피 증시", "부동산 물가"]

_SYSTEM = """당신은 한국 개인투자자를 위한 '머니체크업'의 경제 뉴스 정리 필자입니다.
주어진 '네이버 뉴스 헤드라인·요약'만 근거로 오늘의 경제 뉴스 정리글을 씁니다.

엄격한 규칙:
- 주어진 뉴스에 있는 사실만 쓰세요. 없는 수치·전망·해석을 지어내지 마세요.
- 예측·매수/매도 추천 금지. 낚시·과장·단정 금지. 뉴스는 사실만 담백하게 요약.
- 서로 관련된 뉴스는 주제별로 묶어 정리하세요.
- 한국어. 아래 구조를 지키세요:

제목: (오늘 경제 흐름을 담은 담백한 한 줄)

■ 오늘의 경제 요약
- 핵심 흐름 2~3줄

■ 주요 뉴스
- 뉴스 4~7건을 주제별로 한 줄씩 사실 요약

■ 투자자 참고
- 위 사실들이 투자자에게 주는 배경 2~3문장(예측 아님)

※ 이 글은 공개 뉴스를 정리한 정보 제공용이며, 매수·매도 추천이 아닙니다.

추천 태그:
#경제뉴스 #금리 #환율 #코스피 #머니체크업 (주제에 맞게 6~8개)"""


def _gather():
    seen, items = set(), []
    for q in QUERIES:
        for n in naver_news.search(q, display=6, sort="date"):
            t = n["title"]
            if t and t not in seen:
                seen.add(t)
                line = f"- {t}"
                if n["desc"]:
                    line += f" | {n['desc'][:120]}"
                items.append(line)
        if len(items) >= 14:
            break
    return items[:14]


def _call_claude(payload, api_key):
    import claude_status
    body = {"model": MODEL, "max_tokens": 2200, "system": _SYSTEM,
            "messages": [{"role": "user", "content": payload}]}
    r = requests.post(API_URL, headers={
        "x-api-key": api_key, "anthropic-version": "2023-06-01",
        "content-type": "application/json"}, json=body, timeout=120)
    if r.status_code != 200:
        claude_status.record_result("generate_econ_briefing", False,
                                    status_code=r.status_code, response_text=r.text)
        raise RuntimeError(f"Claude API 오류 {r.status_code}: {r.text[:200]}")
    text = "".join(b.get("text", "") for b in r.json().get("content", [])
                   if b.get("type") == "text").strip()
    claude_status.record_result("generate_econ_briefing", bool(text))
    return text


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("::warning::ANTHROPIC_API_KEY 미설정 — 경제 정리글 건너뜀.")
        return
    if not naver_news.enabled():
        print("::warning::NAVER_CLIENT_ID/SECRET 미설정 — 경제 정리글 건너뜀"
              "(developers.naver.com에서 뉴스 검색 API 등록 필요).")
        return
    items = _gather()
    if len(items) < 3:
        print("::warning::수집된 뉴스가 너무 적음 — 생략.")
        return
    today = datetime.now(KST).strftime("%Y-%m-%d")
    payload = ("[네이버 경제 뉴스 헤드라인·요약]\n" + "\n".join(items)
               + f"\n\n위 뉴스만 근거로 오늘({today}) 경제 뉴스 정리글을 써주세요.")
    text = _call_claude(payload, api_key)
    if not text:
        print("::warning::빈 응답 — 생략.")
        return
    text = text.lstrip()
    for pref in ("제목:", "#", "＃"):
        while text.startswith(pref):
            text = text[len(pref):].lstrip()

    day_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "content_out", today)
    os.makedirs(day_dir, exist_ok=True)
    dst = os.path.join(day_dir, "econ_briefing.txt")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")
    print(f"저장: {dst}\n---\n{text[:400]}")


if __name__ == "__main__":
    main()
