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
import generate_kr_briefing

OUT_DIR = "content_out"


def _write_insight(day_dir, title, data, weekly=False):
    """사이트 데일리 브리핑(/insights) 전용 Claude 버전을 insight.txt로 따로 저장한다.
    네이버용 blog_draft.txt는 SEO/조회수 이유로 룰베이스를 유지하되(2026-07-27 롤백),
    사람이 읽는 사이트 브리핑은 자연스러운 산문이 낫다는 요청으로 분리(2026-07-28).
    Claude 실패 시(키 없음·오류) insight.txt를 아예 안 만들고 조용히 넘어간다 —
    그러면 app.py::_read_insight가 blog_draft.txt(룰베이스)로 자동 폴백한다."""
    body = (generate_kr_briefing.generate_weekly_body(data) if weekly
            else generate_kr_briefing.generate_daily_body(data))
    if not body:
        print("사이트 브리핑(insight.txt) — Claude 실패, blog_draft.txt로 폴백")
        return
    with open(os.path.join(day_dir, "insight.txt"), "w", encoding="utf-8") as f:
        f.write(f"{title}\n{'=' * len(title)}\n\n{body}")
    print("사이트 브리핑 저장 완료 (insight.txt · Claude 생성)")


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

    # 1-b) 사이트 데일리 브리핑(/insights) 전용 Claude 버전 — 같은 제목, 같은 data로.
    _write_insight(day_dir, title, data, weekly=False)

    # 인스타 카드뉴스/캡션은 이제 generate_ai_cards.py(AI 배경 카드)가 전담한다 —
    # 옛 룰베이스 cards/ 데크는 폐기(사용자 요청 2026-09-02). 캡션도 ai_card_candidates/
    # 폴더에 함께 생성되므로 여기서는 블로그 초안 + /insights 브리핑만 만든다.
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

    # 1-b) 사이트 데일리 브리핑(/insights) 전용 Claude 주간 버전.
    _write_insight(day_dir, title, data, weekly=True)

    # 카드/캡션은 generate_ai_cards.py가 전담(옛 cards/ 데크 폐기, 2026-09-02).
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
    import sys
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST)
    force = "--force" in sys.argv
    # 과거 빠진 날 먼저 채움(자주 실행돼도 이미 있는 날은 _has_content로 건너뜀)
    _backfill_missing(today)

    # ── 오늘치: 멱등·스케줄 인지 ────────────────────────────────────────────
    # content-catchup.yml이 하루 여러 번 이 스크립트를 돌려 '스케줄 누락'을 복구한다.
    # 그래서 여기서 (a)콘텐츠 없는 날(일요일·평일휴장일)과 (b)이미 만든 오늘을
    # 명시적으로 걸러, 반복 실행돼도 Claude 재호출·커밋 churn이 생기지 않게 한다.
    wd = today.weekday()  # 0=월 … 5=토 6=일
    if wd == 6:
        print("[스킵] 일요일 — 데일리 콘텐츠 없는 날(정상).")
        return
    if wd < 5 and A._is_market_holiday(today):
        print(f"[스킵] 휴장일({today.strftime('%Y-%m-%d')}) — 데일리 콘텐츠 없는 날(정상).")
        return
    if not force and _has_content(today):
        print(f"[스킵] 오늘({today.strftime('%Y-%m-%d')}) 콘텐츠 이미 존재 — "
              f"멱등 스킵(재생성하려면 --force).")
        return

    if wd == 5:  # 토요일 — 주간 마무리
        _main_weekly()
    else:
        _main_daily()


if __name__ == "__main__":
    main()
