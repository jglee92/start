# -*- coding: utf-8 -*-
"""Claude API 호출 성공/실패를 기록하고, 특히 '크레딧 소진'이나 '키 설정 누락'으로
인한 실패는 GitHub Actions 실행 요약(Job Summary)에 눈에 띄게 남긴다 — 지금까지는
API 실패가 그냥 템플릿 폴백으로 조용히 넘어가서, 잔액이 떨어지거나(혹은 이 저장소가
실제로 겪었던 것처럼 워크플로우 env에 키를 안 넘겨서) Claude 문체가 안 나가도 Actions
로그를 직접 열어보지 않는 한 아무도 모르는 문제가 있었음(사용자가 실제로 지적).

generate_kr_briefing.py / generate_kr_card_copy.py / generate_blog_article.py
셋 다 이 모듈을 거쳐서 API 결과를 기록한다(중복 방지 + 세 곳 다 같은 방식으로
집계되도록)."""
from __future__ import annotations
import json
import os

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "claude_api_status.json")

_CREDIT_PHRASES = ["credit balance", "insufficient credit", "purchase credits", "billing"]
_RATE_LIMIT_PHRASES = ["rate_limit", "rate limit", "429"]

_SUMMARY_TITLES = {
    "credit_exhausted": ":warning: Claude API credit balance appears to be exhausted",
    "no_api_key": ":key: ANTHROPIC_API_KEY not set — Claude generation skipped",
    "rate_limited": ":hourglass: Claude API rate limit hit — fell back to template",
}


def classify_failure(status_code, response_text):
    """API 실패 원인을 대략 분류 — Anthropic 에러 메시지 문구 기준(문구가 바뀌면
    못 잡을 수 있지만, 크레딧 소진 메시지는 상당히 고정적인 문구라 실용적으로 충분).
    호출부가 API를 아예 안 부른 경우(키 없음)는 별도로 "no_api_key"를 직접 넘긴다."""
    text = (response_text or "").lower()
    if any(p in text for p in _CREDIT_PHRASES):
        return "credit_exhausted"
    if status_code == 429 or any(p in text for p in _RATE_LIMIT_PHRASES):
        return "rate_limited"
    return "other"


def _load():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"total_calls": 0, "total_success": 0, "total_fallbacks": 0,
            "by_reason": {}, "last_success": None, "last_fallback": None,
            "recent_failures": []}


def _save(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def _write_summary(lines):
    """GITHUB_STEP_SUMMARY는 Actions가 스텝마다 새로 정해주는 파일 경로 — 여기 쓴
    마크다운이 그 실행의 Summary 탭에 그대로 렌더링된다(로컬 실행 등 이 env가 없으면
    조용히 건너뜀)."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def record_result(script, success, status_code=None, response_text=None, reason=None):
    """API 호출(또는 시도) 하나의 결과를 기록.
    success=True면 성공 카운트만 올리고 끝. 실패면 reason이 안 주어졌으면
    classify_failure()로 분류하고, 누적 집계 + (크레딧 소진/키 없음/rate-limit이면)
    Job Summary 경고까지 남긴다."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    state = _load()
    state["total_calls"] += 1

    if success:
        state["total_success"] += 1
        state["last_success"] = now
        _save(state)
        return

    reason = reason or classify_failure(status_code, response_text)
    state["total_fallbacks"] += 1
    state["by_reason"][reason] = state["by_reason"].get(reason, 0) + 1
    state["last_fallback"] = now
    state["recent_failures"] = ([{"time": now, "script": script, "reason": reason,
                                   "status_code": status_code}]
                                 + state.get("recent_failures", []))[:20]
    _save(state)

    title = _SUMMARY_TITLES.get(reason)
    if title:
        _write_summary([
            f"## {title}",
            "",
            f"- Script: `{script}`",
            f"- 이 사유로 인한 누적 폴백: {state['by_reason'][reason]}회"
            f" (전체 폴백 {state['total_fallbacks']}회 중)",
            f"- 마지막 성공 호출: {state.get('last_success') or '기록 없음'}",
            "",
            "콘텐츠 자체는 템플릿으로 정상 생성됐지만, 이 실행부터는 Claude 문체가"
            " 아닙니다." + (" console.anthropic.com에서 크레딧을 확인해주세요."
                          if reason == "credit_exhausted" else ""),
        ])
