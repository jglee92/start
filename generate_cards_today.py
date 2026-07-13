# -*- coding: utf-8 -*-
"""오늘자 카드뉴스 생성 — 수동 실행용(반자동 파이프라인의 '콘텐츠 생성' 단계).
결과물(01.png..0N.png)을 Buffer/Later에 캡션과 함께 직접 올리면 됨."""
from __future__ import annotations

import app as A
import caption_generator
import card_render
import card_templates


def main():
    data = A._blog_draft_data()
    if data["is_holiday"]:
        print("오늘은 휴장일이라 카드뉴스를 만들지 않습니다.")
        return

    date_str = data["date"].strftime("%Y-%m-%d")
    headline_lines, subtitle, tid = card_templates.pick_cover_headline(
        data, A._name_of, date_str)
    print(f"표지 헤드라인 템플릿: {tid}")
    print(f"  {headline_lines} / {subtitle}")

    paths = card_render.generate_cards(data, A._name_of, headline_lines, subtitle,
                                        date_str.replace("-", "."), out_dir="cards_out")
    print(f"\n생성된 카드 {len(paths)}장:")
    for p in paths:
        print(" ", p)

    data_for_caption = dict(data)
    data_for_caption["_name_of"] = A._name_of
    caption = caption_generator.build_caption(data_for_caption, headline_lines, subtitle)
    caption_path = "cards_out/caption.txt"
    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(caption)
    print(f"\n캡션 저장됨: {caption_path}")
    print("---")
    print(caption)


if __name__ == "__main__":
    main()
