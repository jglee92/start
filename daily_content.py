# -*- coding: utf-8 -*-
"""매 평일 07:30 KST + 토요일 아침에 GitHub Actions로 자동 실행 — 블로그 초안 +
인스타 카드뉴스/캡션을 한 번에 만들어 content_out/YYYY-MM-DD/에 날짜별로 저장하고
커밋한다(지난 콘텐츠도 기록으로 남겨두고 싶다는 요청 반영 — 다만 매일 폴더가 쌓이므로
레포 용량이 계속 늘어남(하루치 약 400~500KB). 너무 쌓이면 오래된 날짜 폴더는 주기적으로
정리 필요). 토요일엔 send_newsletter.py와 같은 방식으로 '주간 마무리' 콘텐츠로 분기
(_weekly_wrap_data 기반) — post_to_instagram.py는 날짜 폴더만 보고 게시하므로 이
분기와 무관하게 그대로 재사용된다. 평일 휴장일엔 아무것도 만들지 않고 조용히 종료."""
from __future__ import annotations
import os

import app as A
import caption_generator
import card_render
import card_templates

OUT_DIR = "content_out"


def _main_daily():
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
    caption = caption_generator.build_caption(data, headline_lines, subtitle, date_str)
    with open(os.path.join(cards_dir, "caption.txt"), "w", encoding="utf-8") as f:
        f.write(caption)
    print("캡션 저장 완료")
    print(f"\n저장 위치: {day_dir}")


def _main_weekly():
    data = A._weekly_wrap_data()
    date_str = data["date"].strftime("%Y-%m-%d")
    day_dir = os.path.join(OUT_DIR, date_str)
    os.makedirs(day_dir, exist_ok=True)

    # 1) 블로그 초안(주간 마무리) — 뉴스레터(send_newsletter.py)와 같은 텍스트
    title, body = A._weekly_wrap_text(data)
    with open(os.path.join(day_dir, "blog_draft.txt"), "w", encoding="utf-8") as f:
        f.write(f"{title}\n{'=' * len(title)}\n\n{body}")
    print("주간 블로그 초안 저장 완료")

    # 2) 인스타 카드뉴스 + 캡션
    headline_lines, subtitle, tid = card_templates.pick_weekly_cover_headline(data, date_str)
    cards_dir = os.path.join(day_dir, "cards")
    paths = card_render.generate_weekly_cards(data, headline_lines, subtitle,
                                               date_str.replace("-", "."), out_dir=cards_dir)
    print(f"주간 카드뉴스 {len(paths)}장 저장 완료 (표지 템플릿: {tid})")

    caption = caption_generator.build_weekly_caption(data, headline_lines, subtitle, date_str)
    with open(os.path.join(cards_dir, "caption.txt"), "w", encoding="utf-8") as f:
        f.write(caption)
    print("캡션 저장 완료")
    print(f"\n저장 위치: {day_dir}")


def main():
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    is_saturday = datetime.now(KST).weekday() == 5  # 0=월요일 ... 5=토요일
    if is_saturday:
        _main_weekly()
    else:
        _main_daily()


if __name__ == "__main__":
    main()
