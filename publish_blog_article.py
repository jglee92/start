# -*- coding: utf-8 -*-
"""
에버그린(오래 유효한) 블로그 글을 3일에 1편씩 발행(드립)한다.

매일 브리핑(daily_content.py)은 실시간 데이터를 템플릿에 채우는 자동생성이지만,
투자 기초 지식 같은 교육글은 사람이 직접 써야 질이 나온다(템플릿으로 찍어내면
'얇은 콘텐츠'가 됨). 그래서 여기서는 미리 써둔 글을 큐에 쌓아두고, 이 스크립트가
3일 간격으로 큐에서 다음 글을 꺼내 그날 content_out/ 폴더로 복사만 한다.
아침 sync_content.bat이 로컬로 받아가면 네이버 블로그에 복붙하면 된다.

- 큐:   blog_articles/queue.txt (발행 순서, blog_articles/ 기준 상대경로)
- 상태: data/blog_article_state.json (마지막 발행일 + 발행 완료 목록)
- 간격: INTERVAL_DAYS (기본 3일) — 워크플로우는 매일 돌지만 여기서 게이트한다.

사용: python publish_blog_article.py
"""
from __future__ import annotations
import os
import sys
import json
import shutil
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8")

KST = timezone(timedelta(hours=9))
BASE = os.path.dirname(os.path.abspath(__file__))
ARTICLES_DIR = os.path.join(BASE, "blog_articles")
QUEUE_PATH = os.path.join(ARTICLES_DIR, "queue.txt")
STATE_PATH = os.path.join(BASE, "data", "blog_article_state.json")
INTERVAL_DAYS = 3


def load_queue():
    items = []
    with open(QUEUE_PATH, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                items.append(s)
    return items


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"last_published": None, "published": []}


def save_state(st):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def main():
    today = datetime.now(KST).date()
    st = load_state()
    last = st.get("last_published")
    if last:
        gap = (today - datetime.strptime(last, "%Y-%m-%d").date()).days
        if gap < INTERVAL_DAYS:
            print(f"아직 발행 간격({INTERVAL_DAYS}일) 안 됨 — 마지막 발행 {last}, {gap}일 경과. 스킵.")
            return

    queue = load_queue()
    published = set(st.get("published", []))
    nxt = next((p for p in queue if p not in published), None)
    if not nxt:
        print("::warning::큐에 발행할 새 글이 없습니다. blog_articles/에 글을 추가하고 queue.txt에 등록하세요.")
        return

    src = os.path.join(ARTICLES_DIR, *nxt.split("/"))
    if not os.path.exists(src):
        print(f"::error::큐에 등록됐지만 실제 파일이 없습니다: {nxt}")
        sys.exit(1)

    day_dir = os.path.join(BASE, "content_out", today.strftime("%Y-%m-%d"))
    os.makedirs(day_dir, exist_ok=True)
    dst = os.path.join(day_dir, f"교육글_{os.path.basename(nxt)}")
    shutil.copyfile(src, dst)

    st["last_published"] = today.strftime("%Y-%m-%d")
    st.setdefault("published", []).append(nxt)
    save_state(st)

    remaining = sum(1 for p in queue if p not in set(st["published"]))
    print(f"발행 완료: {nxt}")
    print(f"  → {dst}")
    print(f"남은 큐: {remaining}편")
    if remaining <= 1:
        print("::warning::큐가 거의 소진됐습니다(1편 이하). 다음 세션에 새 글을 채우세요.")


if __name__ == "__main__":
    main()
