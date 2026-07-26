# -*- coding: utf-8 -*-
"""인스타 표지 카드 헤드라인·부제·캡션을 Claude API로 생성 — card_templates.py의
템플릿 로테이션을 대체 시도. generate_kr_briefing.py와 같은 안전장치 철학(실패 시
호출부가 기존 템플릿으로 폴백)이지만, 여기는 추가로 '길이 제약'이라는 하드 제약이
하나 더 있다: 헤드라인은 카드 이미지(card_render.py::render_cover)에 고정 폰트
크기(62pt)로 렌더링되는 텍스트라, 자동 줄바꿈이 없어서 너무 길면 카드 밖으로
넘치거나 잘릴 수 있다. 기존 템플릿들의 실제 헤드라인 길이를 참고해 넉넉하되 안전한
상한을 두고, 그걸 넘으면 폰트/레이아웃을 못 보는 이 환경에서 위험을 감수하는 대신
조용히 실패 처리(호출부가 템플릿으로 폴백)한다."""
from __future__ import annotations
import json
import os

import requests

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"

MAX_HEADLINE_CHARS = 16   # 카드 헤드라인 한 줄 — 기존 템플릿 예시들 기준 여유있게
MAX_SUBTITLE_CHARS = 28   # 부제 — subtitle은 카드에서 2줄까지 자동 줄바꿈되므로 조금 더 여유

_SYSTEM = """당신은 한국 주식 정보 인스타그램 계정 '머니체크업'의 카드뉴스 표지 카피라이터입니다.
아래 오늘의 실제 데이터만 근거로 표지 헤드라인·부제·캡션을 만듭니다.

[제약 — 반드시 지킬 것]
- 헤드라인은 정확히 2줄. 각 줄은 공백 포함 %d자를 절대 넘지 마세요(카드 이미지에 고정
  크기로 렌더링되어 길면 잘립니다). 짧고 임팩트 있게, 숫자를 넣을 수 있으면 넣으세요.
  글자 수 제약이 빡빡하니 헤드라인에서는 종목코드 없이 이름만 써도 됩니다.
- 부제는 한 줄, 공백 포함 %d자 이내.
- 캡션은 3~6줄, 이모지 1~2개 정도 자연스럽게 사용 가능. 캡션에서 특정 종목을 언급할
  때는 "회사명(종목코드)" 형식으로 쓰세요(예: SK이터닉스(475150)) — 데이터에 이미
  "이름(코드)" 형태로 주어집니다.
- 데이터에 없는 숫자·종목·사건을 지어내지 마세요.
- 특정 종목 매수·매도 권유 금지. 자극적이어도 되지만 거짓은 안 됩니다.

[출력 형식] 반드시 아래 JSON만 출력하세요(다른 설명 없이):
{"headline1": "...", "headline2": "...", "subtitle": "...", "caption_lines": ["...", "..."]}
""" % (MAX_HEADLINE_CHARS, MAX_SUBTITLE_CHARS)


def _serialize_brief(data, is_weekly):
    if is_weekly:
        import generate_kr_briefing as gkb
        return gkb._serialize_weekly(data)
    import generate_kr_briefing as gkb
    return gkb._serialize_daily(data)


def _valid(parsed):
    h1, h2 = parsed.get("headline1", ""), parsed.get("headline2", "")
    sub = parsed.get("subtitle", "")
    lines = parsed.get("caption_lines")
    if not (h1 and h2 and sub and isinstance(lines, list) and lines):
        return False
    if len(h1) > MAX_HEADLINE_CHARS or len(h2) > MAX_HEADLINE_CHARS:
        return False
    if len(sub) > MAX_SUBTITLE_CHARS:
        return False
    return True


def generate_card_copy(data, is_weekly=False):
    """(headline_lines[2], subtitle, caption_lines) 또는 실패 시 None.
    길이 제약을 어기거나 API 실패 시 무조건 None — 호출부가 기존 템플릿 로테이션으로
    폴백한다(카드 이미지가 깨지는 것보다 템플릿이 안전)."""
    import claude_status
    script = "generate_kr_card_copy"
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("::warning::ANTHROPIC_API_KEY 미설정 — 카드 템플릿으로 폴백.")
        claude_status.record_result(script, False, reason="no_api_key")
        return None
    context = _serialize_brief(data, is_weekly)
    try:
        r = requests.post(API_URL, headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": MODEL, "max_tokens": 500, "system": _SYSTEM,
            "messages": [{"role": "user",
                          "content": f"오늘 데이터:\n\n{context}\n\n위 JSON 형식으로만 답하세요."}],
        }, timeout=60)
        if r.status_code != 200:
            print(f"::warning::Claude API 오류 {r.status_code} — 카드 템플릿으로 폴백.")
            claude_status.record_result(script, False, status_code=r.status_code, response_text=r.text)
            return None
        parts = [b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text"]
        text = "".join(parts).strip()
        # 코드펜스로 감싸 답하는 경우 방어
        if text.startswith("```"):
            text = text.strip("`").lstrip("json").strip()
        parsed = json.loads(text)
    except Exception as e:
        print(f"::warning::카드 카피 생성 실패: {type(e).__name__}: {e} — 템플릿으로 폴백.")
        claude_status.record_result(script, False, response_text=str(e))
        return None

    if not _valid(parsed):
        print("::warning::Claude 카드 카피가 길이 제약을 벗어남 — 템플릿으로 폴백.")
        claude_status.record_result(script, False, reason="other")
        return None

    claude_status.record_result(script, True)
    return [parsed["headline1"], parsed["headline2"]], parsed["subtitle"], parsed["caption_lines"]
