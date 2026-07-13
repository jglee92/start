# -*- coding: utf-8 -*-
"""매일 07:30 KST에 GitHub Actions로 자동 실행 — 블로그 초안 + 인스타 카드뉴스/캡션을
한 번에 만들어 content_out/에 저장하고 커밋한다(날짜별로 쌓지 않고 최신 것만 덮어써서
레포 용량 관리 — 필요하면 워크플로 로그/git history에서 예전 것도 볼 수 있음).
휴장일엔 아무것도 만들지 않고 조용히 종료."""
from __future__ import annotations
import os

import app as A
import caption_generator
import card_render
import card_templates

OUT_DIR = "content_out"


def main():
    data = A._blog_draft_data()
    if data["is_holiday"]:
        print("휴장일 — 오늘은 콘텐츠를 만들지 않습니다.")
        return

    os.makedirs(OUT_DIR, exist_ok=True)

    # 1) 블로그 초안
    title, body = A._blog_draft_text()
    with open(os.path.join(OUT_DIR, "blog_draft.txt"), "w", encoding="utf-8") as f:
        f.write(f"{title}\n{'=' * len(title)}\n\n{body}")
    print("블로그 초안 저장 완료")

    # 2) 인스타 카드뉴스 + 캡션 (같은 구조화 데이터 재사용, 텍스트 재파싱 없음)
    date_str = data["date"].strftime("%Y-%m-%d")
    headline_lines, subtitle, tid = card_templates.pick_cover_headline(data, A._name_of, date_str)
    cards_dir = os.path.join(OUT_DIR, "cards")
    paths = card_render.generate_cards(data, A._name_of, headline_lines, subtitle,
                                        date_str.replace("-", "."), out_dir=cards_dir)
    print(f"카드뉴스 {len(paths)}장 저장 완료 (표지 템플릿: {tid})")

    data["_name_of"] = A._name_of
    caption = caption_generator.build_caption(data, headline_lines, subtitle)
    with open(os.path.join(cards_dir, "caption.txt"), "w", encoding="utf-8") as f:
        f.write(caption)
    print("캡션 저장 완료")


if __name__ == "__main__":
    main()
