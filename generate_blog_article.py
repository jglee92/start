# -*- coding: utf-8 -*-
"""
Claude API로 교육글 한 편을 생성한다(큐가 비었을 때 publish_blog_article.py가 호출).

매일 브리핑처럼 데이터로 찍는 게 아니라 '글쓰기'라서, 미리 정해둔 주제 백로그
(blog_articles/topics.txt)에서 다음 주제를 골라 Claude에게 쓰게 한다. 생성된 글은
사람이 손으로 쓴 글과 똑같은 위치/형식으로 저장되고 queue.txt에 등록돼, 드립
발행 대상이 된다. 톤·정확성·면책·머니체크업 맥락은 시스템 프롬프트로 강하게 고정.

정확성 보증은 못 하므로(AI 생성), 네이버에 올리기 전 사람이 한 번 훑어보는 게
안전장치다(수동 게시라 그 단계에서 걸러짐).

필요: 환경변수 ANTHROPIC_API_KEY (GitHub Secret로 주입).
사용: python generate_blog_article.py   (단독 실행 시 주제 1편 생성)
"""
from __future__ import annotations
import os
import re
import sys
import json

import requests

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
ARTICLES_DIR = os.path.join(BASE, "blog_articles")
TOPICS_PATH = os.path.join(ARTICLES_DIR, "topics.txt")
QUEUE_PATH = os.path.join(ARTICLES_DIR, "queue.txt")
STATE_PATH = os.path.join(BASE, "data", "blog_article_state.json")

# 모델 ID — 필요시 여기만 바꾸면 됨. 교육글엔 sonnet이 품질·비용 균형이 좋다.
MODEL = "claude-sonnet-5"
API_URL = "https://api.anthropic.com/v1/messages"

_SYSTEM = """당신은 한국 개인투자자를 위한 투자 교육 블로그 '머니체크업'의 필자입니다.
네이버 블로그에 올릴 교육글 한 편을 씁니다.

[독자와 톤]
- 주식을 이제 막 배우는 사람도 이해할 수 있게, 친근하고 쉬운 말투로.
- 하지만 근거 있고 정직하게. 과장·단정·수익 보장·"이러면 무조건 오른다" 같은 표현은
  절대 쓰지 마세요. 특정 종목을 언급하거나 추천하지 마세요.
- 예시를 들 때는 가상의 상황이나 일반론으로(실제 특정 기업명 금지).

[분량] 공백 포함 1500~2200자 정도.

[출력 형식] 아래 형식을 '정확히' 지키고, 다른 설명 없이 글 본문만 출력하세요:

[카테고리: {category}]

제목: (여기에 제목 — 물음표로 끝나는 질문형이 좋음)

─────────────────────────────────────

(도입: 독자가 겪는 흔한 오해나 상황으로 시작하는 한두 문단)

■ (소제목)

(본문. 필요하면 ① ② ③ 로 항목 나열, 들여쓴 예시 사용)

■ (소제목)
...

■ 마무리

(핵심 요약 한두 문단. 그다음 머니체크업을 자연스럽게 한 문단으로 연결 —
"머니체크업(https://getmoneycheckup.com)에서는 ..." 식으로, 이 글 주제와 관련된
기능(PER·ROE·부채비율·회계감사의견·건강점수 별점 등)을 억지스럽지 않게 언급. 사이트
주소는 항상 https://를 붙여서 쓰세요.)


※ 이 글은 투자 교육·정보 제공용이며, 특정 종목에 대한 매수·매도 추천이 아닙니다.
   투자 판단과 책임은 본인에게 있습니다.


─────────────────────────────────────
추천 태그:
(주제에 맞는 해시태그 8~10개, 마지막은 #머니체크업)
"""


def _load_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]


def _load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"last_published": None, "published": [], "generated_topics": []}


def _save_state(st):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def _slug(topic):
    s = re.sub(r"[?!.,·:/\\\"'()\[\]]", "", topic).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:80]


def _next_topic(st):
    used = set(st.get("generated_topics", []))
    for line in _load_lines(TOPICS_PATH):
        if "|" not in line:
            continue
        folder, topic = (x.strip() for x in line.split("|", 1))
        key = f"{folder}|{topic}"
        if key not in used:
            return folder, topic, key
    return None


def _category_name(folder):
    # "01_투자기초기" -> "투자기초기"
    return re.sub(r"^\d+_", "", folder)


def _call_claude(category, topic, api_key):
    body = {
        "model": MODEL,
        "max_tokens": 3000,
        "system": _SYSTEM.replace("{category}", category),
        "messages": [{
            "role": "user",
            "content": f"카테고리: {category}\n주제: {topic}\n\n이 주제로 교육글 한 편을 써주세요.",
        }],
    }
    r = requests.post(API_URL, headers={
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }, json=body, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Claude API 오류 {r.status_code}: {r.text[:300]}")
    data = r.json()
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    text = "".join(parts).strip()
    if not text:
        raise RuntimeError("Claude 응답이 비어 있음")
    return text


def generate_one():
    """다음 주제로 글 1편 생성 → 파일 저장 + queue.txt 등록 + 상태 기록.
    반환: 생성된 글의 blog_articles/ 기준 상대경로. 생성 못 하면 None."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("::warning::ANTHROPIC_API_KEY 미설정 — 자동 생성 건너뜀.")
        return None
    st = _load_state()
    nt = _next_topic(st)
    if not nt:
        print("::warning::topics.txt에 남은 주제가 없습니다. 주제를 더 추가하세요.")
        return None
    folder, topic, key = nt
    category = _category_name(folder)
    print(f"생성 시작: [{category}] {topic}")
    text = _call_claude(category, topic, api_key)

    out_dir = os.path.join(ARTICLES_DIR, folder)
    os.makedirs(out_dir, exist_ok=True)
    rel = f"{folder}/{_slug(topic)}.txt"
    dst = os.path.join(ARTICLES_DIR, *rel.split("/"))
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")

    with open(QUEUE_PATH, "a", encoding="utf-8") as f:
        f.write(rel + "\n")

    st.setdefault("generated_topics", []).append(key)
    _save_state(st)
    print(f"생성 완료: {rel}  (queue.txt 등록됨)")
    return rel


if __name__ == "__main__":
    generate_one()
