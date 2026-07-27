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
import generate_kr_card_copy

OUT_DIR = "content_out"


def _main_daily(target_date=None):
    """target_date 지정 시(빠진 날짜 보정용) — _blog_draft_data() 자체는 항상 '지금'
    기준 시세·공시로 계산되므로(그 시점 데이터를 되돌릴 방법은 없음), 저장 폴더명·
    제목만 target_date로 바꿔치기한다. 즉 완전한 시점정합 백필이 아니라 "그날 못
    만들어진 걸 최대한 비슷한 최신 데이터로 뒤늦게 채워 넣는" 수준의 보정 —
    개인 블로그 규모에서는 하루이틀 차이 데이터로도 충분하다고 판단."""
    data = A._blog_draft_data()
    if data["is_holiday"]:
        print("휴장일 — 오늘은 콘텐츠를 만들지 않습니다.")
        return
    if target_date is not None:
        data["date"] = target_date

    date_str = data["date"].strftime("%Y-%m-%d")
    day_dir = os.path.join(OUT_DIR, date_str)
    os.makedirs(day_dir, exist_ok=True)

    # 1) 블로그 초안 — Claude 전환 후 조회수가 급감해 템플릿으로 롤백(사용자 확인,
    # 2026-07-27). 인스타 카드 카피(아래 2번)는 Claude 유지.
    title, body = A._blog_draft_text()
    with open(os.path.join(day_dir, "blog_draft.txt"), "w", encoding="utf-8") as f:
        f.write(f"{title}\n{'=' * len(title)}\n\n{body}")
    print("블로그 초안 저장 완료")

    # 2) 인스타 카드뉴스 + 캡션 (같은 구조화 데이터 재사용, 텍스트 재파싱 없음)
    # 헤드라인은 카드 이미지에 고정폰트로 렌더링되는 텍스트라 길이 위반 시 카드가
    # 깨질 수 있음 — Claude 결과가 길이 제약을 못 지키면 조용히 템플릿으로 폴백.
    data["_name_of"] = A._name_of
    card_copy = generate_kr_card_copy.generate_card_copy(data, is_weekly=False)
    if card_copy:
        headline_lines, subtitle, caption_lines = card_copy
        tid = "claude"
        caption = "\n".join([" ".join(headline_lines), subtitle, ""] + caption_lines
                             + caption_generator._closing_lines(date_str, "daily"))
        print("카드 카피 (Claude 생성)")
    else:
        headline_lines, subtitle, tid = card_templates.pick_cover_headline(data, A._name_of, date_str)
        caption = caption_generator.build_caption(data, headline_lines, subtitle, date_str)
        print(f"카드 카피 (템플릿 폴백: {tid})")

    cards_dir = os.path.join(day_dir, "cards")
    paths = card_render.generate_cards(data, A._name_of, headline_lines, subtitle,
                                        date_str.replace("-", "."), out_dir=cards_dir)
    print(f"카드뉴스 {len(paths)}장 저장 완료 (표지 템플릿: {tid})")

    with open(os.path.join(cards_dir, "caption.txt"), "w", encoding="utf-8") as f:
        f.write(caption)
    print("캡션 저장 완료")
    print(f"\n저장 위치: {day_dir}")


def _main_weekly(target_date=None):
    """target_date 지정 시(빠진 토요일 보정용) — _main_daily()와 같은 이유로
    저장 폴더명·제목만 바꿔치기(완전한 시점정합 백필은 아님)."""
    data = A._weekly_wrap_data()
    if target_date is not None:
        data["date"] = target_date
    date_str = data["date"].strftime("%Y-%m-%d")
    day_dir = os.path.join(OUT_DIR, date_str)
    os.makedirs(day_dir, exist_ok=True)

    # 1) 블로그 초안(주간 마무리) — 뉴스레터(send_newsletter.py)와 같은 텍스트.
    # 일간과 동일하게 템플릿으로 롤백(위 _main_daily 주석 참고).
    title, body = A._weekly_wrap_text(data)
    with open(os.path.join(day_dir, "blog_draft.txt"), "w", encoding="utf-8") as f:
        f.write(f"{title}\n{'=' * len(title)}\n\n{body}")
    print("주간 블로그 초안 저장 완료")

    # 2) 인스타 카드뉴스 + 캡션
    card_copy = generate_kr_card_copy.generate_card_copy(data, is_weekly=True)
    if card_copy:
        headline_lines, subtitle, caption_lines = card_copy
        tid = "claude"
        caption = "\n".join([" ".join(headline_lines), subtitle, ""] + caption_lines
                             + caption_generator._closing_lines(date_str, "weekly"))
        print("카드 카피 (Claude 생성)")
    else:
        headline_lines, subtitle, tid = card_templates.pick_weekly_cover_headline(data, date_str)
        caption = caption_generator.build_weekly_caption(data, headline_lines, subtitle, date_str)
        print(f"카드 카피 (템플릿 폴백: {tid})")

    cards_dir = os.path.join(day_dir, "cards")
    paths = card_render.generate_weekly_cards(data, headline_lines, subtitle,
                                               date_str.replace("-", "."), out_dir=cards_dir)
    print(f"주간 카드뉴스 {len(paths)}장 저장 완료 (표지 템플릿: {tid})")

    with open(os.path.join(cards_dir, "caption.txt"), "w", encoding="utf-8") as f:
        f.write(caption)
    print("캡션 저장 완료")
    print(f"\n저장 위치: {day_dir}")


def _has_content(date):
    return os.path.isfile(os.path.join(OUT_DIR, date.strftime("%Y-%m-%d"), "blog_draft.txt"))


def _backfill_missing(today, lookback_days=6):
    """오늘보다 전날짜 중 콘텐츠가 빠진 날을 찾아 뒤늦게 채운다 — 워크플로우가 그날
    한 번 실패했거나(스케줄 미실행·일시 오류) 폴더가 지워진 경우 대비. 매일 이 검사가
    돌므로 보통 빠짐이 감지되면 하루 안에 채워짐 — 그래서 '완전한 시점정합 백필'
    대신 최신 데이터로 대충 채우는 타협(_main_daily/_main_weekly의 target_date 인자
    참고)이 실용적으로 괜찮다고 판단."""
    from datetime import timedelta
    for i in range(1, lookback_days + 1):
        d = today - timedelta(days=i)
        if d.weekday() == 6:  # 일요일 — 콘텐츠 없는 게 정상
            continue
        if d.weekday() == 5:  # 토요일 — 주간 마무리 대상
            if not _has_content(d):
                print(f"[백필] {d.strftime('%Y-%m-%d')}(토) 콘텐츠 누락 감지 — 재생성")
                _main_weekly(target_date=d)
            continue
        if A._is_market_holiday(d):  # 평일이지만 그날 자체가 휴장일이면 원래도 안 만듦
            continue
        if not _has_content(d):
            print(f"[백필] {d.strftime('%Y-%m-%d')} 콘텐츠 누락 감지 — 재생성")
            _main_daily(target_date=d)


def main():
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST)
    _backfill_missing(today)
    is_saturday = today.weekday() == 5  # 0=월요일 ... 5=토요일
    if is_saturday:
        _main_weekly()
    else:
        _main_daily()


if __name__ == "__main__":
    main()
