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

엄격한 규칙(절대 어기지 마세요 — 헤드라인은 제목 한 줄뿐이라 근거가 매우 얇습니다.
빈 곳을 상상으로 채우고 싶어질 텐데, 그 유혹을 참는 게 이 작업에서 가장 중요합니다):
- 모든 문장은 아래 번호 매긴 헤드라인 중 최소 하나에 직접 대응돼야 합니다. 헤드라인에
  없는 원인·결론·전망·배경 설명을 지어내지 마세요.
- "~것으로 보인다", "~것으로 판단됩니다", "~것으로 추정됩니다" 같은 추측성 표현 금지 —
  헤드라인이 명시하지 않은 이유·의도를 짐작해서 쓰지 마세요. 확실치 않으면 아예 쓰지 마세요.
- 서로 다른 사안을 하나의 인과관계처럼 엮지 마세요. 같은 묶음(주제)에는 실제로 같은
  사안을 다루는 헤드라인만 넣고, 우연히 같은 검색어로 걸린 무관한 헤드라인을 억지로
  같이 묶지 마세요.
- 수치(%, 원, 억, 조 등 단위 포함)는 헤드라인에 적힌 그대로만 옮기세요. 단위를 임의로
  바꾸거나(예: 억↔조), 어림잡아 다른 숫자로 바꾸지 마세요. 헤드라인에 숫자가 없으면
  숫자를 만들어내지 마세요.
- 특정인·기관의 발언이나 전망은 사실처럼 단정하지 말고 "~라는 분석이 나옵니다",
  "~라고 밝혔습니다"처럼 누가 한 말인지 드러나게 쓰세요.
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


_VERIFY_SYSTEM = """당신은 '머니체크업' 경제 정리글의 팩트체커입니다. [원본 헤드라인]과
[초안]을 비교해, 초안에서 헤드라인으로 뒷받침 안 되는 부분만 최소한으로 고칩니다.

반드시 고칠 것:
- 헤드라인 어디에도 없는 원인·결론·전망을 지어낸 문장(예: "~것으로 보인다", "~것으로
  판단됩니다" 같은 추측)은 삭제하거나, 헤드라인이 실제로 뒷받침하는 문장으로 바꾸세요.
- 서로 무관한 사안을 하나의 인과관계처럼 엮은 문장은 분리하거나 삭제하세요.
- 수치(%, 원, 억, 조 등)가 해당 헤드라인과 다르면 헤드라인 값으로 정정하세요.
- 특정인·기관의 발언·전망이 사실처럼 단정돼 있으면 "~라고 밝혔습니다"처럼 출처가
  드러나게 고치세요.

하지 말 것:
- 문제 없는 문장까지 다시 쓰거나 표현을 바꾸지 마세요(최소 수정 원칙).
- 형식(제목 줄, ■ 오늘 한눈에, ■ 주제별 정리, ■ 오늘의 한 문장, 추천 태그, 마크다운
  금지 등)은 그대로 유지하세요.
- 설명·주석·"수정했습니다" 같은 메타 코멘트 없이, 완성된 전체 글만 그대로 출력하세요."""


def _gather():
    seen, items = set(), []
    for q in QUERIES:
        try:
            for n in A._google_news(q)[:5]:
                t = (n.get("title") or "").strip()
                if t and t not in seen:
                    seen.add(t)
                    src = n.get("source") or ""
                    items.append(f"{t}" + (f" ({src})" if src else ""))
        except Exception:
            pass
        if len(items) >= 14:
            break
    return items[:14]


def _numbered(items):
    return "\n".join(f"{i+1}. {t}" for i, t in enumerate(items))


def _call_claude(payload, api_key, system=_SYSTEM, label="generate_econ_briefing"):
    import claude_status
    body = {"model": MODEL, "max_tokens": 2800, "system": system,
            "messages": [{"role": "user", "content": payload}]}
    r = requests.post(API_URL, headers={
        "x-api-key": api_key, "anthropic-version": "2023-06-01",
        "content-type": "application/json"}, json=body, timeout=120)
    if r.status_code != 200:
        claude_status.record_result(label, False,
                                    status_code=r.status_code, response_text=r.text)
        raise RuntimeError(f"Claude API 오류 {r.status_code}: {r.text[:200]}")
    text = "".join(b.get("text", "") for b in r.json().get("content", [])
                   if b.get("type") == "text").strip()
    claude_status.record_result(label, bool(text))
    return text


def _verify(draft, items, api_key):
    """생성된 초안을 같은 헤드라인 목록과 대조해 사실 아닌 문장을 최소 수정으로 정리하는
    2차 패스. 헤드라인이 제목 한 줄뿐이라 근거가 얇아 1차 생성만으로는 추측성 문장이
    섞이기 쉬움(사용자가 실제로 틀린 부분을 지적해 도입, 2026-09-04). 실패해도 원본
    초안으로 계속 진행(교정 실패가 게시 자체를 막지 않게)."""
    payload = (f"[원본 헤드라인]\n{_numbered(items)}\n\n[초안]\n{draft}\n\n"
               "위 규칙대로 최소 수정만 적용한 완성본을 출력해주세요.")
    try:
        fixed = _call_claude(payload, api_key, system=_VERIFY_SYSTEM,
                             label="generate_econ_briefing_verify")
        return fixed or draft
    except Exception as e:
        print(f"::warning::검증 패스 실패 — 1차 초안 그대로 사용: {e}")
        return draft


# 경제 정리글에 곁들일 AI 배경 카드(글자 없는 배경 + 한국어 제목 합성). 카드/합성
# 로직은 generate_ai_cards의 것을 재사용해 브랜드 톤을 통일한다. 키 없으면 폴백 배경.
_ECON_SCENE = ("an early-morning economic briefing desk by a window overlooking a calm "
               "modern city skyline at sunrise, a folded newspaper and a cup of coffee, "
               "warm soft editorial light, sense of a quiet start to the day")


def _make_card(title, today):
    try:
        import generate_ai_cards as GC
    except Exception as e:
        print(f"::warning::카드 모듈 로드 실패 — 카드 생략: {e}")
        return
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "content_out", today, "ai_card_candidates")
    os.makedirs(out_dir, exist_ok=True)
    bgs = GC._gen_backgrounds(GC._prompt(_ECON_SCENE), 1)
    bg = bgs[0] if bgs else GC._fallback_bg(0)
    if not bgs:
        print("  [econ] 이미지 API 미설정/실패 — 폴백 배경 사용.")
    # 헤드라인은 브랜드 고정 문구(정리글 제목은 길이가 들쭉날쭉해 부제로 배치).
    card = GC._compose(bg, ["오늘의 경제", "뉴스 정리"], title, today.replace("-", "."))
    p = os.path.join(out_dir, "econ.png")
    card.save(p)
    print(f"  저장: {p}")


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("::warning::ANTHROPIC_API_KEY 미설정 — 경제 정리글 건너뜀.")
        return
    today = datetime.now(KST).strftime("%Y-%m-%d")
    # 멱등 스킵 — GitHub 스케줄 드롭 대비용 catchup 백스톱이 하루 여러 번 이 스크립트를
    # 돌려도, 이미 성공한 날은 Claude를 두 번(생성+검증) 다시 호출하지 않게 한다.
    # kr_screener/daily_content.py의 _has_content 패턴과 동일(2026-09-04 도입).
    _dst_check = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "content_out", today, "ai_card_candidates", "econ_briefing.txt")
    if "--force" not in sys.argv and os.path.isfile(_dst_check):
        print(f"[스킵] 오늘({today}) 경제 정리글 이미 존재 — 멱등 스킵(재생성하려면 --force).")
        return
    items = _gather()
    if len(items) < 3:
        print("::warning::수집된 뉴스가 너무 적음 — 생략.")
        return
    payload = ("[경제 뉴스 헤드라인]\n" + _numbered(items)
               + f"\n\n위 헤드라인만 근거로 오늘({today}) 경제 뉴스 정리글을 써주세요.")
    text = _call_claude(payload, api_key)
    if not text:
        print("::warning::빈 응답 — 생략.")
        return
    # 2차 검증 패스 — 같은 헤드라인과 대조해 추측성 문장·인과 왜곡·수치 오류를 정리.
    text = _verify(text, items, api_key)
    # 네이버 평문화: 마크다운 헤딩(#)·강조(*, **) 제거(모델이 종종 섞어 씀).
    text = text.replace("**", "")
    # 마크다운 헤딩(# 뒤 공백)만 제거. '#경제뉴스' 같은 해시태그(# 뒤 글자)는 보존.
    text = re.sub(r"(?m)^\s*#{1,6}[ \t]+", "", text)
    text = text.replace("*", "")                # 남은 이탤릭 마커
    text = text.lstrip()
    for pref in ("제목:", "＃"):
        while text.startswith(pref):
            text = text[len(pref):].lstrip()

    # 카드(econ.png)와 같은 폴더에 넣어 함께 게시하기 쉽게 한다(사용자 요청 2026-09-04).
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "content_out", today, "ai_card_candidates")
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, "econ_briefing.txt")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")
    print(f"저장: {dst}\n---\n{text[:400]}")

    # 블로그에 곁들일 AI 배경 카드 1장(제목을 부제로). 실패해도 정리글엔 영향 없음.
    title = next((ln.strip() for ln in text.splitlines() if ln.strip()),
                 "오늘의 경제 뉴스 정리")
    try:
        _make_card(title, today)
    except Exception as e:
        print(f"::warning::경제 카드 생성 실패(정리글은 정상): {e}")


if __name__ == "__main__":
    main()
