# -*- coding: utf-8 -*-
"""매일 아침 뉴스레터(블로그 초안과 동일 내용)를 Resend Broadcast로 자동 발송.
GitHub Actions에서 평일 08:30 KST에 실행(daily-prices보다 늦게: 전날 저녁 갱신된
데이터를 그대로 재사용). 휴장일에는 보낼 실질 내용이 없으므로 아예 스킵한다.

구독취소 링크는 Resend가 {{{RESEND_UNSUBSCRIBE_URL}}} 플레이스홀더를 자동으로
실제 구독취소 URL로 치환해준다(발신자가 직접 처리할 필요 없음)."""
from __future__ import annotations
import html as html_mod
import os
import sys
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import requests
import app as A

KST = timezone(timedelta(hours=9))
FROM_ADDR = "머니체크업 <news@getmoneycheckup.com>"


def _to_html(title, body):
    paras = [f"<p><b>{html_mod.escape(title)}</b></p>"]
    for line in body.split("\n"):
        if not line.strip():
            paras.append("<p>&nbsp;</p>")
            continue
        indent = len(line) - len(line.lstrip(" "))
        escaped = html_mod.escape(line.lstrip(" "))
        paras.append(f"<p>{'&nbsp;' * indent}{escaped}</p>")
    paras.append(
        '<p style="margin-top:22px;padding-top:14px;border-top:1px solid #ddd;'
        'font-size:12px;color:#8a94a3">이 메일은 머니체크업 뉴스레터 구독자에게 '
        '발송됩니다. 더 이상 받고 싶지 않으시면 '
        '<a href="{{{RESEND_UNSUBSCRIBE_URL}}}">여기서 구독을 취소</a>하실 수 있습니다.</p>'
    )
    return "\n".join(paras)


def main():
    now = datetime.now(KST)
    if A._is_market_holiday(now):
        print(f"{now.date()}는 휴장일이라 뉴스레터를 보내지 않습니다.")
        return

    api_key = os.getenv("RESEND_API_KEY")
    audience_id = os.getenv("RESEND_AUDIENCE_ID")
    if not api_key or not audience_id:
        print("RESEND_API_KEY / RESEND_AUDIENCE_ID 미설정 - 발송 스킵")
        return

    title, body = A._blog_draft_text()
    r = requests.post(
        "https://api.resend.com/broadcasts",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "audience_id": audience_id,
            "from": FROM_ADDR,
            "subject": title,
            "html": _to_html(title, body),
            "send": True,
        },
        timeout=20,
    )
    if r.status_code == 422 and "no contacts" in r.text:
        print("구독자가 아직 없어 발송을 건너뜁니다.")
        return
    r.raise_for_status()
    print(f"발송 완료: {r.json()}")


if __name__ == "__main__":
    main()
