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
    +457% 같은 압도적인 숫자가 있는데 earnings_split(건수 요약)이 뽑혀서 묻히는 걸 방지.
    임팩트는 80에서 상한(실적은 최근 1개월 내 '과거' 공시라, 코스피 폭락처럼 '오늘'
    일어난 시장 전체 이슈보다 과하게 세게 잡히면 안 돼서 — 퍼센트가 아무리 커도
    개별종목 실적 하나가 시장 급락보다 항상 이기는 건 부자연스러움)."""
    cands = [e for e in data["earnings"] if e.get("ni_yoy") is not None]
    top = max(cands, key=lambda e: abs(e["ni_yoy"]))
    sign = "+" if top["ni_yoy"] >= 0 else ""
    word = "실적 서프라이즈" if top["ni_yoy"] >= 0 else "어닝쇼크"
    return ([f"{top['name']} 순이익 {sign}{top['ni_yoy']:.0f}%", word],
            "오늘 실적 발표, 서프라이즈부터 쇼크까지 총정리", min(abs(top["ni_yoy"]), 80))


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


KOSPI_MOVE_MIN = 1.0   # 이 이상 움직여야 후보에 듦(평범한 ±0.수%는 아예 후보 제외)
FX_MOVE_MIN = 0.5


def _t_kospi_move(data):
    """코스피/코스닥 당일 등락 — 실적(분기 전 데이터)보다 훨씬 시의성 있는 '오늘'
    소식이라, 크게 흔들린 날엔 다른 템플릿보다 우선 뽑히도록 임팩트에 배율(18배)을
    준다. _eligible()에서 KOSPI_MOVE_MIN 이상일 때만 후보로 들어오므로, 사소한
    변동에는 아예 뽑히지 않고(다른 템플릿에 자리를 내줌) 진짜 급등락일 때만 경쟁."""
    ix = data["us_indices"]
    cands = [(ix[k]["name"], ix[k]["chg_pct"]) for k in ("kospi", "kosdaq")
             if ix.get(k) and ix[k].get("chg_pct") is not None]
    name, pct = max(cands, key=lambda c: abs(c[1]))
    mood = "급등" if pct >= 0 else "급락"
    sign = "+" if pct >= 0 else ""
    return ([f"{name} 오늘 {sign}{pct:.1f}%", f"{mood}, 무슨 일이?"],
            "오늘 국내 증시 흐름 한눈에 정리", abs(pct) * 30)


def _t_fx_move(data):
    """원달러 환율 급변 — 이것도 '오늘' 소식이라 실적류보다 우선순위를 높게(28배).
    FX_MOVE_MIN 미만이면 애초에 후보로 안 들어옴."""
    usd = data["us_indices"]["usdkrw"]
    pct = usd["chg_pct"]
    mood = "급등" if pct >= 0 else "급락"
    sign = "+" if pct >= 0 else ""
    return ([f"원달러 환율 오늘 {sign}{pct:.1f}%", mood],
            f"{usd['price']:,.1f}원 — 오늘 환율·증시 체크", abs(pct) * 35)


def _detect_trend(data):
    """kr_trend(app.py::_kr_index_streak 결과)에서 '며칠 하락 끝에 반등' /
    '상승 흐름 속 오늘 조정' 패턴을 찾는다. returns의 마지막 값이 오늘, 그 앞 4개가
    최근 4거래일. 오늘이 그 앞 연속 흐름과 반대 방향이고 그 연속이 2일 이상이면 감지.
    코스피·코스닥 둘 다 감지되면 연속일수가 더 긴 쪽을 우선. 없으면 None."""
    best = None
    for key in ("kospi", "kosdaq"):
        t = (data.get("kr_trend") or {}).get(key)
        if not t or len(t["returns"]) < 5:
            continue
        today = t["returns"][-1]
        prior = t["returns"][:-1]
        if today > 0:
            streak, kind = 0, "rebound"
        elif today < 0:
            streak, kind = 0, "correction"
        else:
            continue
        opposite = (lambda r: r < 0) if kind == "rebound" else (lambda r: r > 0)
        for r in reversed(prior):
            if opposite(r):
                streak += 1
            else:
                break
        if streak >= 2 and (best is None or streak > best[2]):
            best = (t["name"], kind, streak, today)
    return best


def _t_rebound(data):
    name, _kind, streak, today = data["_trend"]
    sign = "+" if today >= 0 else ""
    return ([f"{name} {streak}일 하락 끝에", f"오늘 {sign}{today:.1f}% 반등"],
            "며칠간 눌렸던 지수, 드디어 반등하나", 10 + streak * 6)


def _t_correction(data):
    name, _kind, streak, today = data["_trend"]
    return ([f"{name} {streak}일 연속 상승 후", f"오늘 {today:.1f}%, 조정 시작?"],
            "상승장 속 첫 흔들림, 조정일까 숨고르기일까", 10 + streak * 6)


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
    ("kospi_move", ["_kr_index"], _t_kospi_move),
    ("fx_move", ["_fx"], _t_fx_move),
    ("rebound", ["_rebound"], _t_rebound),
    ("correction", ["_correction"], _t_correction),
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
        if req == "_kr_index":
            ix = data.get("us_indices") or {}
            moves = [abs(ix[k]["chg_pct"]) for k in ("kospi", "kosdaq")
                     if ix.get(k) and ix[k].get("chg_pct") is not None]
            if not moves or max(moves) < KOSPI_MOVE_MIN:
                return False
            continue
        if req == "_fx":
            ix = data.get("us_indices") or {}
            usd = ix.get("usdkrw")
            if not (usd and usd.get("chg_pct") is not None and usd.get("price")
                    and abs(usd["chg_pct"]) >= FX_MOVE_MIN):
                return False
            continue
        if req == "_rebound":
            if not (data.get("_trend") and data["_trend"][1] == "rebound"):
                return False
            continue
        if req == "_correction":
            if not (data.get("_trend") and data["_trend"][1] == "correction"):
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
    data["_trend"] = _detect_trend(data)

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
