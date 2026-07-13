# -*- coding: utf-8 -*-
"""인스타 카드뉴스 표지(01번 카드) 헤드라인 로테이션.
매일 같은 문구("이 3개 안 보면 손해봅니다")만 나오면 팔로워가 질리므로, 여러
클릭베이트 템플릿을 두고 그날 데이터로 채울 수 있는 것만 후보로 추린 뒤, 그 중
가장 자극적인(숫자가 큰) 것부터 고른다 — 예전엔 후보 중 무작위였는데, 그러면
'순이익 +457%' 같은 훨씬 세게 어필하는 숫자가 있어도 '테마수익률 +14.5%' 같은
약한 게 뽑힐 수 있었음(2026-07-13 실제로 발생, 사용자 지적으로 발견). 최근
NO_REPEAT_DAYS일 안에 쓴 템플릿 '형태'는 피해서 로테이션도 유지."""
from __future__ import annotations
import json
import os

HISTORY_PATH = "data/cover_history.json"
NO_REPEAT_DAYS = 7


def _fmt_pct(v):
    return f"{abs(v):.0f}"


# needs: data 안에 반드시 있어야 하는 값(빈 리스트/None이면 후보에서 제외)
# fill(data) -> (headline_2lines, subtitle, impact) — impact: 헤드라인에 쓴 핵심 숫자의
# 절대값(클수록 자극적). 데이터 의존 없는 안전 템플릿은 낮은 고정값을 준다.
def _t_gainer_pct(data):
    top = data["gainers"][0]
    name = data["_name_of"](top[0])
    return ([f"{name} +{_fmt_pct(top[1])}%,", "오늘 급등주 TOP3"],
            "장 시작 전 급등·급락 종목 한눈에 정리", abs(top[1]))


def _t_earnings_extreme(data):
    """실적 중 순이익 증감률(ni_yoy)이 가장 극단적인(서프라이즈든 쇼크든) 1건을 헤드라인에.
    +457% 같은 압도적인 숫자가 있는데 earnings_split(건수 요약)이 뽑혀서 묻히는 걸 방지."""
    cands = [e for e in data["earnings"] if e.get("ni_yoy") is not None]
    top = max(cands, key=lambda e: abs(e["ni_yoy"]))
    sign = "+" if top["ni_yoy"] >= 0 else ""
    word = "실적 서프라이즈" if top["ni_yoy"] >= 0 else "어닝쇼크"
    return ([f"{top['name']} 순이익 {sign}{top['ni_yoy']:.0f}%", word],
            "오늘 실적 발표, 서프라이즈부터 쇼크까지 총정리", abs(top["ni_yoy"]))


def _t_earnings_split(data):
    n_s = sum(1 for e in data["earnings"] if e["tag"] == "surprise")
    n_k = sum(1 for e in data["earnings"] if e["tag"] == "shock")
    return (["실적 발표에서", "웃은 회사, 울은 회사"],
            f"어닝서프라이즈 {n_s}곳 · 어닝쇼크 {n_k}곳 정리", 12)


def _t_anomaly_count(data):
    n = len(data["anomalies"])
    return ([f"오늘 이상신호 {n}건,", "조심해야 할 종목은?"],
            "적자전환 등 재무 위험신호 무료 확인", 10 + n * 3)


def _t_theme_hot(data):
    top = data["themes"][0]
    sign = "+" if top["ret_1m"] >= 0 else ""
    return ([f"요즘 뜨는 테마 '{top['mid']}'", f"한 달 수익률 {sign}{top['ret_1m']:.1f}%"],
            "지금 주도테마·특징테마 총정리", abs(top["ret_1m"]))


def _t_us_market(data):
    ix = data["us_indices"]
    nasdaq = ix.get("nasdaq")
    up = nasdaq and nasdaq.get("chg_pct", 0) >= 0
    mood = "웃었다" if up else "울었다"
    return ([f"간밤 미국 증시는 {mood},", "오늘 국내 증시는?"],
            "장 시작 전 5분, 미국장·환율 체크", 6)


def _t_five_things(data):
    return (["오늘 장 시작 전", "꼭 봐야 할 5가지"],
            "코스피·코스닥 실적·특징테마 한눈에 정리", 5)


def _t_dont_miss(data):
    return (["장 열리기 전 5분 투자,", "오늘 놓치면 아쉬운 소식"],
            "급등주부터 이상신호까지 한 번에", 5)


TEMPLATES = [
    # (id, requires: list[str] - data키가 비어있지 않아야 함, fill함수)
    ("gainer_pct", ["gainers"], _t_gainer_pct),
    ("earnings_extreme", ["_earnings_ni"], _t_earnings_extreme),
    ("earnings_split", ["earnings"], _t_earnings_split),
    ("anomaly_count", ["anomalies"], _t_anomaly_count),
    ("theme_hot", ["themes"], _t_theme_hot),
    ("us_market", ["us_indices"], _t_us_market),
    ("five_things", [], _t_five_things),
    ("dont_miss", [], _t_dont_miss),
]


def _load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_history(hist):
    os.makedirs(os.path.dirname(HISTORY_PATH) or ".", exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(hist[-60:], f, ensure_ascii=False, indent=1)  # 최근 60건만 보관


def _eligible(tid, requires, data):
    for req in requires:
        if req == "_earnings_ni":
            if not any(e.get("ni_yoy") is not None for e in data["earnings"]):
                return False
            continue
        if not data.get(req):
            return False
    return True


def pick_cover_headline(data, name_of, today_str):
    """data: _blog_draft_data() 반환값. name_of: 종목코드->이름 함수(순환 참조 방지로
    인자로 받음). today_str: 'YYYY-MM-DD' — 중복 방지 히스토리 기록용.
    반환: (headline_lines, subtitle, template_id) — 오늘 쓸 수 있는 템플릿 중
    가장 임팩트(숫자) 큰 걸 우선 고르되, 최근 NO_REPEAT_DAYS일 안에 쓴 템플릿
    '형태'는 후보에서 제외해 로테이션을 유지한다."""
    data = dict(data)
    data["_name_of"] = name_of

    hist = _load_history()
    recent_ids = {h["template_id"] for h in hist if h["date"] >= _days_ago(today_str, NO_REPEAT_DAYS)}

    candidates = [(tid, fill) for tid, requires, fill in TEMPLATES if _eligible(tid, requires, data)]
    if not candidates:
        candidates = [("five_things", _t_five_things)]

    fresh = [(tid, fill) for tid, fill in candidates if tid not in recent_ids]
    pool = fresh or candidates  # 전부 최근에 썼으면 그냥 후보 전체에서(순환)

    filled = [(tid, *fill(data)) for tid, fill in pool]  # (tid, lines, subtitle, impact)
    filled.sort(key=lambda x: x[3], reverse=True)
    tid, lines, subtitle, _impact = filled[0]

    hist.append({"date": today_str, "template_id": tid})
    _save_history(hist)
    return lines, subtitle, tid


def _days_ago(date_str, n):
    from datetime import date, timedelta
    y, m, d = map(int, date_str.split("-"))
    cutoff = date(y, m, d) - timedelta(days=n)
    return cutoff.isoformat()
