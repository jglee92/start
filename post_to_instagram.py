# -*- coding: utf-8 -*-
"""daily_content.py가 만든 카드뉴스를 인스타그램에 캐러셀로 자동 게시.
이미지는 daily-content.yml이 이미 content_out/YYYY-MM-DD/cards/에 커밋+푸시해둔
뒤라 raw.githubusercontent.com URL로 바로 공개 접근 가능(별도 호스팅 불필요,
확인 완료: 2026-07-13 카드로 실제 200 OK 응답 확인함).

Graph API 3단계: (1) 이미지마다 캐러셀 아이템 컨테이너 생성 (2) 그 컨테이너들을
묶어 캐러셀 컨테이너 생성 (3) 발행. 토큰/계정ID는 환경변수로 받음(시크릿).

필요 환경변수:
  INSTAGRAM_ACCESS_TOKEN — Meta 개발자 앱에서 발급한 장기 페이지 액세스 토큰
  INSTAGRAM_BUSINESS_ID  — 인스타 비즈니스 계정의 Graph API user id(숫자)
  GITHUB_REPOSITORY      — 'owner/repo' (raw URL 조립용, GitHub Actions가 자동 제공)
"""
from __future__ import annotations
import os
import sys
import time

import requests

API = "https://graph.facebook.com/v21.0"


def _raw_url(repo, branch, path):
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"


def _post(path, **params):
    r = requests.post(f"{API}/{path}", params=params, timeout=30)
    if not r.ok:
        raise RuntimeError(f"Graph API 오류 {r.status_code}: {r.text}")
    return r.json()


def publish_carousel(image_urls, caption, access_token, ig_user_id):
    if not (2 <= len(image_urls) <= 10):
        raise ValueError(f"캐러셀은 2~10장만 가능(받은 장수: {len(image_urls)})")

    item_ids = []
    for url in image_urls:
        d = _post(f"{ig_user_id}/media", image_url=url, is_carousel_item="true",
                   access_token=access_token)
        item_ids.append(d["id"])
        time.sleep(1)  # 컨테이너가 FINISHED 상태로 넘어갈 시간 여유

    carousel = _post(f"{ig_user_id}/media", media_type="CAROUSEL",
                      children=",".join(item_ids), caption=caption, access_token=access_token)
    time.sleep(2)

    published = _post(f"{ig_user_id}/media_publish", creation_id=carousel["id"],
                       access_token=access_token)
    return published


def main():
    access_token = os.environ["INSTAGRAM_ACCESS_TOKEN"]
    ig_user_id = os.environ["INSTAGRAM_BUSINESS_ID"]
    repo = os.environ.get("GITHUB_REPOSITORY", "jglee92/start")
    branch = os.environ.get("GITHUB_REF_NAME", "main")

    date_str = sys.argv[1] if len(sys.argv) > 1 else None
    if not date_str:
        from datetime import datetime, timezone, timedelta
        KST = timezone(timedelta(hours=9))
        date_str = datetime.now(KST).strftime("%Y-%m-%d")

    cards_dir = f"content_out/{date_str}/cards"
    if not os.path.isdir(cards_dir):
        print(f"{cards_dir} 없음 — 오늘 콘텐츠가 생성되지 않은 날(휴장일 등)로 보고 종료")
        return

    files = sorted(f for f in os.listdir(cards_dir) if f.endswith(".png"))
    image_urls = [_raw_url(repo, branch, f"content_out/{date_str}/cards/{f}") for f in files]
    with open(os.path.join(cards_dir, "caption.txt"), "r", encoding="utf-8") as f:
        caption = f.read()

    print(f"게시 대상 {len(image_urls)}장: {image_urls}")
    result = publish_carousel(image_urls, caption, access_token, ig_user_id)
    print(f"게시 완료: {result}")


if __name__ == "__main__":
    main()
