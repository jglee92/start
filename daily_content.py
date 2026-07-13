# -*- coding: utf-8 -*-
"""매일 07:30 KST에 GitHub Actions로 자동 실행 — 블로그 초안 + 인스타 카드뉴스/캡션을
한 번에 만들어 content_out/YYYY-MM-DD/에 날짜별로 저장하고 커밋한다(지난 콘텐츠도
기록으로 남겨두고 싶다는 요청 반영 — 다만 매일 폴더가 쌓이므로 레포 용량이 계속
늘어남(하루치 약 400~500KB). 너무 쌓이면 오래된 날짜 폴더는 주기적으로 정리 필요).
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

    date_str = data["date"].strftime("%Y-%m-%d")
    day_dir = os.path.join(OUT_DIR, date_str)
    os.makedirs(day_dir, exist_ok=True)

    # 1) 블로그 초안
    title, body = A._blog_draft_text()
    with open(os.path.join(day_dir, "blog_draft.txt"), "w", encoding="utf-8") as f:
        f.write(f"{title}\n{'=' * len(title)}\n\n{body}")
    print("블로그 초안 저장 완료")

    # 2) 인스타 카드뉴스 + 캡션 (같은 구조화 데이터 재사용, 텍스트 재파싱 없음)
    headline_lines, subtitle, tid = card_templates.pick_cover_headline(data, A._name_of, date_str)
    cards_dir = os.path.join(day_dir, "cards")
    paths = card_render.generate_cards(data, A._name_of, headline_lines, subtitle,
                                        date_str.replace("-", "."), out_dir=cards_dir)
    print(f"카드뉴스 {len(paths)}장 저장 완료 (표지 템플릿: {tid})")

    data["_name_of"] = A._name_of
    caption = caption_generator.build_caption(data, headline_lines, subtitle)
    with open(os.path.join(cards_dir, "caption.txt"), "w", encoding="utf-8") as f:
        f.write(caption)
    print("캡션 저장 완료")
    print(f"\n저장 위치: {day_dir}")


if __name__ == "__main__":
    main()
