# -*- coding: utf-8 -*-
"""'오늘의 경제 뉴스 정리' 일일 드래프트 — 구글뉴스(키 불필요)로 한국 경제 뉴스를
모아 Claude(haiku)가 사실 위주로 하루치 정리글을 쓴다. 네이버 블로그 등에 매일 쌓는 용도.

(네이버 뉴스 검색 API는 2026년 현재 개발자센터 애플리케이션 등록 메뉴에서 발급이
빠져 사용 불가 → 이미 쓰던 app._google_news(구글뉴스 RSS, 무키)로 대체. 목표는 동일.)

근거는 '뉴스 헤드라인'만. 예측·매수매도·낚시 금지(정직 브랜드).
출력: content_out/<date>/econ_briefing.txt (제목 첫 줄 + 본문, 붙여넣기용).
필요: ANTHROPIC_API_KEY.
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timezone, timedelta

import re

import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import app as A

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"
KST = timezone(timedelta(hours=9))

QUERIES = ["한국 경제", "금리 환율", "코스피 증시", "부동산 물가"]

_SYSTEM = """당신은 '머니체크업'의 경제 뉴스 해설 필자입니다. 주어진 '뉴스 헤드라인'만
근거로, 경제를 잘 모르는 개인투자자도 이해하기 쉬운 '교육형 경제 정리글'을 씁니다.

엄격한 규칙(절대 어기지 마세요):
- 주어진 헤드라인에 있는 사실만 쓰세요. 없는 수치·전망·해석을 지어내지 마세요.
- 예측·매수/매도 추천 금지. 낚시·과장·단정 금지.

문체·구성:
- 친근하고 차분한 톤(뉴스레터처럼). 어려운 용어(국채금리, 부채비율, 기준금리 등)는
  괄호로 짧게 풀어 설명해 초보자도 읽히게 하세요.
- 관련 뉴스는 주제별로 묶고, 각 묶음 끝에 "쉽게 말하면" 한 줄로 배경·의미를 사실에
  근거해 덧붙이세요(예측이 아니라 '왜 이런 뉴스가 나오는지/무엇을 뜻하는지' 설명).
- 마크다운 문법(#, *, ** 등)을 절대 쓰지 마세요 — 네이버 블로그용 평문입니다.
- 한국어. 아래 구조를 정확히 지키세요:

제목: (오늘 경제 흐름을 담은 담백한 한 줄. 낚시 금지)

(첫 줄: 친근한 인사 한 문장 — 예: "오늘 아침 경제 흐름, 쉽게 정리해드려요.")

■ 오늘 한눈에
- 핵심 흐름 2~3줄

■ 주제별 정리
(있는 주제만: 금리·환율 / 증시 / 부동산·물가 / 정책 등)
- 각 주제: 관련 뉴스 사실 요약 몇 줄 + "쉽게 말하면: ..." 한 줄 해설

■ 오늘의 한 문장
- 초보 투자자가 기억하면 좋을 핵심을 사실 위주로 한 문장

※ 이 글은 공개 뉴스를 정리한 정보 제공·교육용이며, 매수·매도 추천이 아닙니다.

추천 태그:
#경제뉴스 #금리 #환율 #코스피 #경제공부 #머니체크업 (주제에 맞게 6~8개)"""


def _gather():
    seen, items = set(), []
    for q in QUERIES:
        try:
            for n in A._google_news(q)[:5]:
                t = (n.get("title") or "").strip()
                if t and t not in seen:
                    seen.add(t)
                    src = n.get("source") or ""
                    items.append(f"- {t}" + (f" ({src})" if src else ""))
        except Exception:
            pass
        if len(items) >= 14:
            break
    return items[:14]


def _call_claude(payload, api_key):
    import claude_status
    body = {"model": MODEL, "max_tokens": 2800, "system": _SYSTEM,
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
    items = _gather()
    if len(items) < 3:
        print("::warning::수집된 뉴스가 너무 적음 — 생략.")
        return
    today = datetime.now(KST).strftime("%Y-%m-%d")
    payload = ("[경제 뉴스 헤드라인]\n" + "\n".join(items)
               + f"\n\n위 헤드라인만 근거로 오늘({today}) 경제 뉴스 정리글을 써주세요.")
    text = _call_claude(payload, api_key)
    if not text:
        print("::warning::빈 응답 — 생략.")
        return
    # 네이버 평문화: 마크다운 헤딩(#)·강조(*, **) 제거(모델이 종종 섞어 씀).
    text = text.replace("**", "")
    text = re.sub(r"(?m)^\s*#+\s*", "", text)   # 줄머리 # 헤딩 마커
    text = text.replace("*", "")                # 남은 이탤릭 마커
    text = text.lstrip()
    for pref in ("제목:", "＃"):
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
