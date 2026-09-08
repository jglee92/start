# -*- coding: utf-8 -*-
"""'오늘의 경제 뉴스 정리' 일일 드래프트 — 구글뉴스(키 불필요)로 한국 경제 뉴스를
모아 Claude(haiku)가 사실 위주로 하루치 정리글을 쓴다. 네이버 블로그 등에 매일 쌓는 용도.

(네이버 뉴스 검색 API는 2026년 현재 개발자센터 애플리케이션 등록 메뉴에서 발급이
빠져 사용 불가 → 이미 쓰던 app._google_news(구글뉴스 RSS, 무키)로 대체. 목표는 동일.)

근거는 '뉴스 헤드라인'만. 예측·매수매도·낚시 금지(정직 브랜드).
출력: content_out/<date>/econ_briefing.txt (제목 첫 줄 + 본문, 붙여넣기용).
필요: ANTHROPIC_API_KEY.
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timezone, timedelta

import re

import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import app as A
import card_templates

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"
KST = timezone(timedelta(hours=9))

QUERIES = ["한국 경제", "금리 환율", "코스피 증시", "부동산 물가"]
# 사설·칼럼 전용 검색어 — 매체 논조/관점 차이를 보여주는 새 섹션용 재료(2026-09-08,
# 사용자 제안). 본문을 가져오는 게 아니라 헤드라인만 짧게 인용+출처 표기하므로
# 기존 '제목+출처' 수집 방식의 연장선이라 저작권 리스크가 낮다.
OPINION_QUERIES = ["경제 사설", "증시 칼럼"]

_SYSTEM = """당신은 '머니체크업'의 경제 뉴스 해설 필자입니다. 주어진 '뉴스 헤드라인'
(그리고 있다면 '오늘의 시장 데이터'·'사설·칼럼 헤드라인')만 근거로, 경제를 잘 모르는
개인투자자도 이해하기 쉬운 '교육형 경제 정리글'을 씁니다.

입력 자료 3종의 성격이 다릅니다 — 반드시 구분해서 다루세요:
1. [오늘의 시장 데이터]: 머니체크업 자체 시스템이 계산한 실제 수치(코스피/코스닥
   등락률, 환율, 강세테마 등). 검증된 사실이니 그대로 인용해도 됩니다. 다만 이
   숫자에서 원인·전망을 새로 지어내진 마세요(예: "환율이 X% 올랐다"까지는 사실,
   "그래서 내일도 오를 것"은 지어낸 전망).
2. [경제 뉴스 헤드라인]: 사실 보도. 아래 규칙대로 사실 위주로만 옮기세요.
3. [사설·칼럼 헤드라인]: 해당 매체의 주장·논조이지 확정된 사실이 아닙니다. 반드시
   "OO일보는 사설에서 '헤드라인 원문'이라고 짚었습니다"처럼 매체명을 밝히고 헤드라인
   문구를 따옴표로 짧게 인용하세요. 그 사설이 왜 그렇게 주장했는지, 본문에 뭐라고
   더 썼을지는 헤드라인에 없으므로 지어내지 마세요. 여러 매체의 논조가 갈리면
   ("A는 낙관적, B는 신중론") 그 차이 자체를 사실적으로 보여주되, 어느 쪽이 맞는지
   당신이 판단하지 마세요.

엄격한 규칙(절대 어기지 마세요 — 뉴스 헤드라인은 제목 한 줄뿐이라 근거가 매우
얇습니다. 빈 곳을 상상으로 채우고 싶어질 텐데, 그 유혹을 참는 게 가장 중요합니다):
- 모든 문장은 위 자료 중 최소 하나에 직접 대응돼야 합니다. 자료에 없는 원인·결론·
  전망·배경 설명을 지어내지 마세요.
- "~것으로 보인다", "~것으로 판단됩니다", "~것으로 추정됩니다" 같은 추측성 표현 금지 —
  자료가 명시하지 않은 이유·의도를 짐작해서 쓰지 마세요. 확실치 않으면 아예 쓰지 마세요.
- 서로 다른 사안을 하나의 인과관계처럼 엮지 마세요. 같은 묶음(주제)에는 실제로 같은
  사안을 다루는 자료만 넣고, 우연히 같은 검색어로 걸린 무관한 헤드라인을 억지로
  같이 묶지 마세요.
- 수치(%, 원, 억, 조 등 단위 포함)는 자료에 적힌 그대로만 옮기세요. 단위를 임의로
  바꾸거나(예: 억↔조), 어림잡아 다른 숫자로 바꾸지 마세요. 자료에 숫자가 없으면
  숫자를 만들어내지 마세요.
- 특정인·기관의 발언이나 전망은 사실처럼 단정하지 말고 "~라는 분석이 나옵니다",
  "~라고 밝혔습니다"처럼 누가 한 말인지 드러나게 쓰세요.
- 예측·매수/매도 추천 금지. 낚시·과장·단정 금지.

문체·구성:
- 친근하고 차분한 톤(뉴스레터처럼). 어려운 용어(국채금리, 부채비율, 기준금리 등)는
  괄호로 짧게 풀어 설명해 초보자도 읽히게 하세요.
- 관련 뉴스는 주제별로 묶고, 각 묶음 끝에 "쉽게 말하면" 한 줄로 배경·의미를 사실에
  근거해 덧붙이세요(예측이 아니라 '왜 이런 뉴스가 나오는지/무엇을 뜻하는지' 설명).
  [오늘의 시장 데이터]가 주어졌다면 관련 주제(증시·환율 등) 문단에 실제 수치를
  자연스럽게 녹여서 두께를 더하세요.
- 마크다운 문법(#, *, ** 등)을 절대 쓰지 마세요 — 네이버 블로그용 평문입니다.
- 한국어. 아래 구조를 정확히 지키세요:

제목: (오늘 경제 흐름을 담은 담백한 한 줄. 낚시 금지)

(첫 줄: 친근한 인사 한 문장 — 예: "오늘 아침 경제 흐름, 쉽게 정리해드려요.")

■ 오늘 한눈에
- 핵심 흐름 2~3줄([오늘의 시장 데이터]가 있으면 코스피/환율 등 숫자 포함)

■ 주제별 정리
(있는 주제만: 금리·환율 / 증시 / 부동산·물가 / 정책 등)
- 각 주제: 관련 뉴스·시장 데이터 사실 요약 몇 줄 + "쉽게 말하면: ..." 한 줄 해설

■ 오늘의 논조
([사설·칼럼 헤드라인]이 주어졌을 때만 이 섹션을 쓰세요. 없으면 생략.)
- 매체명 + 헤드라인 원문을 따옴표로 짧게 인용 1~3개. 여러 관점이 있으면 대비해서
  보여주되 어느 쪽이 옳다고 판단하지 마세요.

■ 오늘의 한 문장
- 초보 투자자가 기억하면 좋을 핵심을 사실 위주로 한 문장

※ 이 글은 공개 뉴스를 정리한 정보 제공·교육용이며, 매수·매도 추천이 아닙니다.

추천 태그:
#경제뉴스 #금리 #환율 #코스피 #경제공부 #머니체크업 (주제에 맞게 6~8개)"""


_VERIFY_SYSTEM = """당신은 '머니체크업' 경제 정리글의 팩트체커입니다. 주어진 원본 자료
([오늘의 시장 데이터]/[원본 뉴스 헤드라인]/[원본 사설·칼럼 헤드라인])와 [초안]을
비교해, 초안에서 원본으로 뒷받침 안 되는 부분만 최소한으로 고칩니다.

반드시 고칠 것:
- 원본 어디에도 없는 원인·결론·전망을 지어낸 문장(예: "~것으로 보인다", "~것으로
  판단됩니다" 같은 추측)은 삭제하거나, 원본이 실제로 뒷받침하는 문장으로 바꾸세요.
- 서로 무관한 사안을 하나의 인과관계처럼 엮은 문장은 분리하거나 삭제하세요.
- 수치(%, 원, 억, 조 등)가 해당 원본과 다르면 원본 값으로 정정하세요. [오늘의 시장
  데이터]에 있는 숫자(코스피·환율 등)가 초안에서 틀리게 옮겨졌으면 바로잡으세요.
- "■ 오늘의 논조" 섹션이 있다면: 인용한 문구가 [원본 사설·칼럼 헤드라인]의 실제
  문구와 다르면 원문에 맞게 고치고, 매체명이 빠져 있으면 추가하세요. 헤드라인에
  없는 내용(그 사설이 왜 그런 주장을 했는지 등)을 지어내 덧붙였으면 삭제하세요.
- 특정인·기관의 발언·전망이 사실처럼 단정돼 있으면 "~라고 밝혔습니다"처럼 출처가
  드러나게 고치세요.

하지 말 것:
- 문제 없는 문장까지 다시 쓰거나 표현을 바꾸지 마세요(최소 수정 원칙).
- 형식(제목 줄, ■ 오늘 한눈에, ■ 주제별 정리, ■ 오늘의 논조(있으면), ■ 오늘의 한 문장,
  추천 태그, 마크다운 금지 등)은 그대로 유지하세요.
- 설명·주석·"수정했습니다" 같은 메타 코멘트 없이, 완성된 전체 글만 그대로 출력하세요."""


# econ_briefing 전용 출처 화이트리스트 — app._is_blocked_source()는 블로그·카페
# 정도만 거르는 넓은 블록리스트라 지역지·군소매체(부산국제신문·인천일보·천지일보·
# 데일리팝·빅터뉴스·코리아리포트, 심지어 Vietnam.vn까지)가 섞여 나왔음. 이제 사설을
# 매체명 붙여 직접 인용하는 "■ 오늘의 논조" 섹션이 있어 출처 신뢰도가 예전보다
# 훨씬 중요해짐(2026-09-08, 사용자 제안) — 여기서만 종합일간지·경제전문지·통신사·
# 지상파로 좁힌다(app.py의 종목별 뉴스 등 다른 용도는 그대로 넓은 필터 유지).
_MAJOR_SOURCES = (
    # 종합일간지
    "조선일보", "중앙일보", "동아일보", "한겨레", "경향신문", "한국일보",
    "서울신문", "국민일보", "문화일보", "세계일보",
    # 경제전문지
    "매일경제", "한국경제", "서울경제", "파이낸셜뉴스", "fnnews",
    "헤럴드경제", "이데일리", "머니투데이", "아시아경제", "조선비즈",
    # 통신사
    "연합뉴스", "뉴시스", "뉴스1",
    # 지상파
    "KBS", "MBC", "SBS", "YTN",
)


def _is_major_source(src):
    s = (src or "").strip()
    return any(k in s for k in _MAJOR_SOURCES)


def _gather_news(seen):
    items = []
    for q in QUERIES:
        try:
            picked = 0
            for n in A._google_news(q):
                if picked >= 5:
                    break
                t = (n.get("title") or "").strip()
                src = n.get("source") or ""
                if not t or t in seen or not _is_major_source(src):
                    continue
                seen.add(t)
                items.append(f"{t}" + (f" ({src})" if src else ""))
                picked += 1
        except Exception:
            pass
        if len(items) >= 14:
            break
    return items[:14]


def _gather_opinions(seen):
    """사설·칼럼 헤드라인 — 매체 논조/관점 차이를 짧은 인용(헤드라인 원문 그대로 +
    출처)으로 보여주기 위한 재료(2026-09-08, 사용자 제안). 본문을 가져오지 않고
    제목만 인용하므로 기존 '제목+출처' 수집 방식의 연장선이라 저작권 리스크가 낮음.
    news와 seen 집합을 공유해 같은 헤드라인이 양쪽에 중복 등장하지 않게 한다."""
    items = []
    for q in OPINION_QUERIES:
        try:
            picked = 0
            for n in A._google_news(q):
                if picked >= 6:
                    break
                t = (n.get("title") or "").strip()
                src = n.get("source") or ""
                if not t or t in seen or not _is_major_source(src):
                    continue
                seen.add(t)
                items.append(f"{t}" + (f" ({src})" if src else ""))
                picked += 1
        except Exception:
            pass
        if len(items) >= 6:
            break
    return items[:6]


def _market_snapshot():
    """오늘의 실제 시장 숫자(코스피/코스닥/환율/간밤 미국지수 + 강세테마) — 우리 DB가
    이미 매일 계산해두는 검증된 수치를 헤드라인과 별도 근거로 얹는다. 헤드라인만으로는
    재료가 얇아 글이 빈약하다는 지적(2026-09-08)에 대응 — 실수치라 추측 없이도
    두께를 더할 수 있다. daily_content.py/generate_ai_cards.py와 같은
    A._blog_draft_data()를 재사용(휴장일 등으로 값이 없으면 조용히 생략)."""
    try:
        data = A._blog_draft_data()
    except Exception as e:
        print(f"::warning::시장 데이터 조회 실패(뉴스만으로 계속): {e}")
        return None
    if not data or data.get("is_holiday"):
        return None
    ix = data.get("us_indices") or {}
    lines = []
    kospi, kosdaq = ix.get("kospi"), ix.get("kosdaq")
    if kospi and kospi.get("chg_pct") is not None:
        lines.append(f"코스피 {kospi['price']:,.2f} ({kospi['chg_pct']:+.2f}%)")
    if kosdaq and kosdaq.get("chg_pct") is not None:
        lines.append(f"코스닥 {kosdaq['price']:,.2f} ({kosdaq['chg_pct']:+.2f}%)")
    usdkrw = ix.get("usdkrw")
    if usdkrw and usdkrw.get("price") is not None:
        chg = f" ({usdkrw['chg_pct']:+.2f}%)" if usdkrw.get("chg_pct") is not None else ""
        lines.append(f"원/달러 환율 {usdkrw['price']:,.1f}원{chg}")
    nasdaq, sp500 = ix.get("nasdaq"), ix.get("sp500")
    if nasdaq and nasdaq.get("chg_pct") is not None:
        lines.append(f"간밤 나스닥 {nasdaq['chg_pct']:+.2f}%")
    if sp500 and sp500.get("chg_pct") is not None:
        lines.append(f"간밤 S&P500 {sp500['chg_pct']:+.2f}%")
    for t in (data.get("themes") or [])[:2]:
        if t.get("ret_1m") is not None:
            lines.append(f"최근 1개월 강세 테마: {t['mid']} ({t['ret_1m']:+.1f}%)")
    return lines or None


def _numbered(items):
    return "\n".join(f"{i+1}. {t}" for i, t in enumerate(items))


def _call_claude(payload, api_key, system=_SYSTEM, label="generate_econ_briefing"):
    import claude_status
    body = {"model": MODEL, "max_tokens": 3500, "system": system,
            "messages": [{"role": "user", "content": payload}]}
    r = requests.post(API_URL, headers={
        "x-api-key": api_key, "anthropic-version": "2023-06-01",
        "content-type": "application/json"}, json=body, timeout=120)
    if r.status_code != 200:
        claude_status.record_result(label, False,
                                    status_code=r.status_code, response_text=r.text)
        raise RuntimeError(f"Claude API 오류 {r.status_code}: {r.text[:200]}")
    text = "".join(b.get("text", "") for b in r.json().get("content", [])
                   if b.get("type") == "text").strip()
    claude_status.record_result(label, bool(text))
    return text


def _verify(draft, items, opinions, market_lines, api_key):
    """생성된 초안을 원본 자료(시장 데이터·뉴스·사설 헤드라인)와 대조해 사실 아닌
    문장을 최소 수정으로 정리하는 2차 패스. 헤드라인이 제목 한 줄뿐이라 근거가 얇아
    1차 생성만으로는 추측성 문장이 섞이기 쉬움(사용자가 실제로 틀린 부분을 지적해
    도입, 2026-09-04; 사설 인용 검증은 2026-09-08 추가). 실패해도 원본 초안으로
    계속 진행(교정 실패가 게시 자체를 막지 않게)."""
    parts = []
    if market_lines:
        parts.append("[오늘의 시장 데이터]\n" + "\n".join(f"- {l}" for l in market_lines))
    parts.append(f"[원본 뉴스 헤드라인]\n{_numbered(items)}")
    if opinions:
        parts.append(f"[원본 사설·칼럼 헤드라인]\n{_numbered(opinions)}")
    payload = ("\n\n".join(parts) + f"\n\n[초안]\n{draft}\n\n"
               "위 규칙대로 최소 수정만 적용한 완성본을 출력해주세요.")
    try:
        fixed = _call_claude(payload, api_key, system=_VERIFY_SYSTEM,
                             label="generate_econ_briefing_verify")
        return fixed or draft
    except Exception as e:
        print(f"::warning::검증 패스 실패 — 1차 초안 그대로 사용: {e}")
        return draft


# 경제 정리글에 곁들일 AI 배경 카드(글자 없는 배경 + 한국어 제목 합성). 카드/합성
# 로직은 generate_ai_cards의 것을 재사용해 브랜드 톤을 통일한다. 키 없으면 폴백 배경.
# 후보를 여러 개 두고 날짜 시드로 로테이션(card_templates._rot 재사용) — 문장이
# 1개뿐이라 매일 거의 같은 그림이 나온다는 지적을 받아 다양화함(2026-09-07).
_ECON_SCENE = [
    "an early-morning economic briefing desk by a window overlooking a calm modern city skyline at sunrise, a folded newspaper and a cup of coffee, warm soft editorial light, sense of a quiet start to the day",
    "a quiet Seoul street at early dawn with soft golden light, calm morning cinematic mood",
    "a folded newspaper and reading glasses on a cafe table by a window, soft morning light, calm editorial mood",
    "an aerial view of the Yeouido financial district at sunrise with soft morning mist, calm editorial mood",
    "a minimalist flat-lay of a coffee cup, notebook, and pen on a wooden table by a window, soft morning light",
]


def _make_card(title, today):
    try:
        import generate_ai_cards as GC
    except Exception as e:
        print(f"::warning::카드 모듈 로드 실패 — 카드 생략: {e}")
        return
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "content_out", today, "econ")
    os.makedirs(out_dir, exist_ok=True)
    scene = card_templates._rot(f"{today}|econ-scene", _ECON_SCENE)
    bgs = GC._gen_backgrounds(GC._prompt(scene), 1)
    bg = bgs[0] if bgs else GC._fallback_bg(0)
    if not bgs:
        print("  [econ] 이미지 API 미설정/실패 — 폴백 배경 사용.")
    # 헤드라인은 브랜드 고정 문구(정리글 제목은 길이가 들쭉날쭉해 부제로 배치).
    card = GC._compose(bg, ["오늘의 경제", "뉴스 정리"], title, today.replace("-", "."))
    p = os.path.join(out_dir, "econ.png")
    card.save(p)
    print(f"  저장: {p}")


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("::warning::ANTHROPIC_API_KEY 미설정 — 경제 정리글 건너뜀.")
        return
    today = datetime.now(KST).strftime("%Y-%m-%d")
    # 멱등 스킵 — GitHub 스케줄 드롭 대비용 catchup 백스톱이 하루 여러 번 이 스크립트를
    # 돌려도, 이미 성공한 날은 Claude를 두 번(생성+검증) 다시 호출하지 않게 한다.
    # kr_screener/daily_content.py의 _has_content 패턴과 동일(2026-09-04 도입).
    _dst_check = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "content_out", today, "econ", "econ_briefing.txt")
    if "--force" not in sys.argv and os.path.isfile(_dst_check):
        print(f"[스킵] 오늘({today}) 경제 정리글 이미 존재 — 멱등 스킵(재생성하려면 --force).")
        return
    seen = set()
    items = _gather_news(seen)
    if len(items) < 3:
        print("::warning::수집된 뉴스가 너무 적음 — 생략.")
        return
    opinions = _gather_opinions(seen)
    market_lines = _market_snapshot()
    print(f"뉴스 {len(items)}건, 사설·칼럼 {len(opinions)}건, "
          f"시장 데이터 {'있음' if market_lines else '없음'}")

    parts = []
    if market_lines:
        parts.append("[오늘의 시장 데이터]\n" + "\n".join(f"- {l}" for l in market_lines))
    parts.append("[경제 뉴스 헤드라인]\n" + _numbered(items))
    if opinions:
        parts.append("[사설·칼럼 헤드라인]\n" + _numbered(opinions))
    payload = ("\n\n".join(parts)
               + f"\n\n위 자료만 근거로 오늘({today}) 경제 뉴스 정리글을 써주세요.")
    text = _call_claude(payload, api_key)
    if not text:
        print("::warning::빈 응답 — 생략.")
        return
    # 2차 검증 패스 — 같은 원본 자료와 대조해 추측성 문장·인과 왜곡·수치 오류·
    # 사설 인용 오류를 정리.
    text = _verify(text, items, opinions, market_lines, api_key)
    # 네이버 평문화: 마크다운 헤딩(#)·강조(*, **) 제거(모델이 종종 섞어 씀).
    text = text.replace("**", "")
    # 마크다운 헤딩(# 뒤 공백)만 제거. '#경제뉴스' 같은 해시태그(# 뒤 글자)는 보존.
    text = re.sub(r"(?m)^\s*#{1,6}[ \t]+", "", text)
    text = text.replace("*", "")                # 남은 이탤릭 마커
    text = text.lstrip()
    for pref in ("제목:", "＃"):
        while text.startswith(pref):
            text = text[len(pref):].lstrip()

    # econ 전용 폴더에 카드(econ.png)와 함께 저장 — 다른 일일 카드(ai_card_candidates)와
    # 섞이지 않는 별도 폴더를 원한다는 사용자 정정 반영(2026-09-04).
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "content_out", today, "econ")
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, "econ_briefing.txt")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")
    print(f"저장: {dst}\n---\n{text[:400]}")

    # 블로그에 곁들일 AI 배경 카드 1장(제목을 부제로). 실패해도 정리글엔 영향 없음.
    title = next((ln.strip() for ln in text.splitlines() if ln.strip()),
                 "오늘의 경제 뉴스 정리")
    try:
        _make_card(title, today)
    except Exception as e:
        print(f"::warning::경제 카드 생성 실패(정리글은 정상): {e}")


if __name__ == "__main__":
    main()
