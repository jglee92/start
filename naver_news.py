# -*- coding: utf-8 -*-
"""네이버 뉴스 검색 API 클라이언트 — openapi.naver.com/v1/search/news.json.
developers.naver.com에서 애플리케이션 등록 후 Client ID/Secret을 환경변수로 넣으면
활성화된다(없으면 enabled()=False → 호출부가 조용히 건너뜀).

Google News RSS(제목만)와 달리 description(요약 스니펫)까지 주므로 뉴스 요약에 유리.
무료 한도 넉넉(일 25,000회). HTML 태그(<b> 등)와 엔티티는 제거해 평문으로 반환.
"""
from __future__ import annotations
import os
import re
import html

import requests

CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
API_URL = "https://openapi.naver.com/v1/search/news.json"


def enabled():
    return bool(CLIENT_ID and CLIENT_SECRET)


def _clean(s):
    s = re.sub(r"<[^>]+>", "", s or "")     # <b> 등 태그 제거
    return html.unescape(s).strip()


def search(query, display=10, sort="date"):
    """query에 대한 뉴스 [{title, desc, link, pub}] (최신순 sort='date' / 정확도 'sim').
    키 없거나 실패 시 []."""
    if not enabled():
        return []
    try:
        r = requests.get(API_URL,
                         headers={"X-Naver-Client-Id": CLIENT_ID,
                                  "X-Naver-Client-Secret": CLIENT_SECRET},
                         params={"query": query, "display": display, "sort": sort},
                         timeout=12)
        if r.status_code != 200:
            print(f"::warning::네이버 뉴스 API {r.status_code}: {r.text[:200]}")
            return []
        out = []
        for it in r.json().get("items", []):
            out.append({
                "title": _clean(it.get("title")),
                "desc": _clean(it.get("description")),
                "link": it.get("originallink") or it.get("link") or "",
                "pub": it.get("pubDate") or "",
            })
        return out
    except Exception as e:
        print(f"::warning::네이버 뉴스 검색 실패: {e}")
        return []
