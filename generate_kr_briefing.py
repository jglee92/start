# -*- coding: utf-8 -*-
"""일간/주간 브리핑 본문을 템플릿 대신 Claude API로 생성 — generate_blog_article.py와
같은 호출 패턴(시스템 프롬프트로 톤·정확성 고정)이지만, 여기는 주제를 골라 쓰게 하는 게
아니라 app.py::_blog_draft_data()/_weekly_wrap_data()가 이미 계산한 오늘의 실제 숫자를
근거로만 쓰게 한다. 호출부(daily_content.py)가 실패 시 기존 템플릿(app.py::_blog_draft_text
등)으로 폴백하므로, 여기서는 실패를 조용히 (None, None)으로 반환하기만 하면 된다 —
라이브 사이트라 이 안전장치가 핵심."""
from __future__ import annotations
import os

import requests

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"

_SYSTEM = """당신은 한국 주식 리서치 사이트 '머니체크업(https://getmoneycheckup.com)'의
장전 브리핑 필자입니다.

[독자와 톤]
- 주식 초보~중급 개인투자자 대상. 친근하고 편안한 말투(반말은 피하고 '~해요'체),
  전문용어는 풀어서.
- 아래 주어진 데이터에 있는 사실만 쓰세요. 숫자·종목명·수치를 지어내지 마세요. 데이터가
  비어 있는 섹션은 자연스럽게 생략하세요.
- 특정 종목을 매수·매도하라고 권유하지 마세요. "무조건 오른다/내린다" 같은 단정도 금지.
- 특정 종목을 처음 언급할 때는 반드시 "회사명(종목코드)" 형식으로 쓰세요(예: SK이터닉스(475150)).
  데이터에 이미 "이름(코드)" 형태로 주어지니 그대로 가져다 쓰면 됩니다 — 종목코드를
  빼고 이름만 쓰지 마세요.
- 사이트 주소는 항상 https://getmoneycheckup.com처럼 https://를 붙여 온전한 링크
  형태로 쓰세요. "getmoneycheckup.com"만 쓰지 마세요.

[분량] 공백 포함 800~1300자.

[출력 형식] 아래 형식을 정확히 지키고, 다른 설명 없이 본문만 출력하세요:

(도입 인사 한두 문장)

■ (소제목 — 데이터에 있는 섹션만, 순서는 자유롭게)
(내용)

■ (소제목)
(내용)

(마무리: 오늘 내용 한 줄 요약 + 머니체크업(https://getmoneycheckup.com) 자연스럽게
한 문단 연결)

※ 매매 추천이 아니며, 투자 판단과 책임은 본인에게 있습니다.

(빈 줄 하나, 그다음 오늘 다룬 내용에 맞는 해시태그 8~10개를 한 줄로 — #국내증시 #코스피
#코스닥은 매번 고정으로 넣고, 나머지는 오늘 등장한 종목·테마·이슈에 맞게 골라서.
마지막은 항상 #머니체크업)
"""


def _fmt_pct(v):
    return f"{v:+.1f}%" if v is not None else "데이터 없음"


def _serialize_daily(data):
    lines = [f"날짜: {data['date'].strftime('%Y-%m-%d')} (장전 체크포인트)"]
    ix = data.get("us_indices") or {}
    if ix:
        lines.append("\n간밤 미국증시:")
        for k in ("nasdaq", "sp500"):
            if ix.get(k) and ix[k].get("chg_pct") is not None:
                lines.append(f"- {ix[k]['name']}: {_fmt_pct(ix[k]['chg_pct'])}")
        if ix.get("usdkrw") and ix["usdkrw"].get("price"):
            lines.append(f"- 원달러 환율: {ix['usdkrw']['price']:,.1f}원")

    gainers, losers = data.get("gainers") or [], data.get("losers") or []
    if gainers or losers:
        # _blog_draft_data()의 gainers/losers는 (code, pct) 튜플뿐이라(이름 미포함) —
        # 실제 라이브 테스트(2026-07-27 첫 생성분)에서 "종목코드 475150"처럼 이름 없이
        # 나온 걸 발견해서 여기서 직접 이름을 붙인다.
        import app as _A
        lines.append(f"\n{data.get('movers_date', '어제')} 급등·급락:")
        for code, pct in gainers:
            lines.append(f"- (급등) {_A._name_of(code)}({code}): {_fmt_pct(pct)}")
        for code, pct in losers:
            lines.append(f"- (급락) {_A._name_of(code)}({code}): {_fmt_pct(pct)}")

    if data.get("earnings"):
        lines.append("\n최근 1개월 내 실적 발표(전년동기대비):")
        for it in data["earnings"]:
            rev = it.get("rev_yoy")
            ni = it.get("ni_yoy")
            tag = " (어닝서프라이즈)" if it.get("tag") == "surprise" else " (어닝쇼크)" if it.get("tag") == "shock" else ""
            lines.append(f"- {it['name']}({it['code']}) {it['year']}년 {it['quarter']}분기: "
                         f"매출 {_fmt_pct(rev)}, 순이익 {_fmt_pct(ni)}{tag}")

    if data.get("anomalies"):
        lines.append("\n재무 이상신호 감지 종목:")
        for a in data["anomalies"]:
            lines.append(f"- {a['name']}({a['code']}) {a['label']}: {a['text']}")

    if data.get("themes"):
        lines.append("\n최근 1개월 강세/약세 테마:")
        for m in data["themes"]:
            lines.append(f"- {m['mid']}: {_fmt_pct(m['ret_1m'])}")
            for t in m.get("sub", []):
                ex = f" (예: {', '.join(t['examples'])})" if t.get("examples") else ""
                lines.append(f"  - {t['name']}: {_fmt_pct(t['ret_1m'])}{ex}")

    featured = data.get("featured")
    if featured:
        lines.append(f"\n오늘의 기업 종합검진 픽: {featured.get('name')}({featured.get('code')})")

    return "\n".join(lines)


def _serialize_weekly(data):
    lines = [f"날짜: {data['date'].strftime('%Y-%m-%d')} (주간 마무리, 금요일 종가 기준)"]
    if data.get("idx"):
        lines.append("\n이번주 주요 지수(1개월 환산 아님, 표기된 기간 그대로):")
        for ix in data["idx"]:
            lines.append(f"- {ix['name']}: {_fmt_pct(ix['chg'])}")

    if data.get("gainers") or data.get("losers"):
        lines.append(f"\n이번주({data.get('week_date', '')}) 급등·급락:")
        for g in data.get("gainers", []):
            lines.append(f"- (급등) {g['name']}({g['code']}): {_fmt_pct(g['pct'])}")
        for l in data.get("losers", []):
            lines.append(f"- (급락) {l['name']}({l['code']}): {_fmt_pct(l['pct'])}")

    if data.get("strong_themes"):
        lines.append("\n이번주 강세 테마:")
        for t in data["strong_themes"]:
            ex = f" (예: {', '.join(t['examples'])})" if t.get("examples") else ""
            lines.append(f"- {t.get('name', t.get('no'))}: {_fmt_pct(t.get('ret_1m'))}{ex}")

    if data.get("anomalies"):
        lines.append("\n지금 재무 이상신호가 켜진 종목(체크해볼 것):")
        for a in data["anomalies"]:
            lines.append(f"- {a['name']}({a['code']}) {a['label']}: {a['text']}")

    if data.get("score_up") or data.get("score_down"):
        lines.append("\n이번주 건강점수 변동:")
        for s in (data.get("score_up") or [])[:3]:
            lines.append(f"- 점수 상승: {s}")
        for s in (data.get("score_down") or [])[:3]:
            lines.append(f"- 점수 하락: {s}")

    return "\n".join(lines)


def _call_claude(context, label):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("::warning::ANTHROPIC_API_KEY 미설정 — 템플릿으로 폴백.")
        return None
    try:
        r = requests.post(API_URL, headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": MODEL, "max_tokens": 1600, "system": _SYSTEM,
            "messages": [{"role": "user",
                          "content": f"아래 데이터만 근거로 오늘의 {label}을 써주세요:\n\n{context}"}],
        }, timeout=120)
        if r.status_code != 200:
            print(f"::warning::Claude API 오류 {r.status_code}: {r.text[:300]} — 템플릿으로 폴백.")
            return None
        parts = [b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text"]
        text = "".join(parts).strip()
        return text or None
    except Exception as e:
        print(f"::warning::Claude API 호출 실패: {type(e).__name__}: {e} — 템플릿으로 폴백.")
        return None


def generate_daily_body(data):
    """본문만 생성(제목은 기존 방식대로 app.py에서 조립 — 형식 일관성 유지). 실패 시 None."""
    return _call_claude(_serialize_daily(data), "장전 체크포인트")


def generate_weekly_body(data):
    return _call_claude(_serialize_weekly(data), "주간 마무리")
