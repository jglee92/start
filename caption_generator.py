# -*- coding: utf-8 -*-
"""인스타 캡션 생성 — 카드뉴스(이미지)와 같은 _blog_draft_data()를 공유해서 쓴다.
이미지 안에는 이모지를 못 쓰지만(폰트 깨짐 문제), 캡션은 인스타 앱 자체가 렌더링하므로
이모지 그대로 써도 안전하다."""
from __future__ import annotations

HASHTAGS = ("#국내증시 #코스피 #코스닥 #오늘의증시 #장전브리핑 #실적발표 "
            "#어닝서프라이즈 #특징주 #특징테마 #머니체크업 #주식 #주식투자 #국내주식 #재테크")


def build_caption(data, headline_lines, subtitle):
    lines = [" ".join(headline_lines), subtitle, ""]

    if data["gainers"]:
        code, pct = data["gainers"][0]
        lines.append(f"\U0001F4C8 오늘의 급등 1위: {data['_name_of'](code)} {pct:+.1f}%")

    n_s = sum(1 for e in data["earnings"] if e["tag"] == "surprise")
    n_k = sum(1 for e in data["earnings"] if e["tag"] == "shock")
    if n_s or n_k:
        lines.append(f"\U0001F4CA 어닝서프라이즈 {n_s}곳 · 어닝쇼크 {n_k}곳")

    if data["anomalies"]:
        lines.append(f"\U0001F6A9 오늘 체크할 이상신호 {len(data['anomalies'])}건")

    if data["themes"]:
        top = data["themes"][0]
        lines.append(f"\U0001F525 요즘 뜨는 테마: {top['mid']} {top['ret_1m']:+.1f}%")

    if data.get("featured"):
        f = data["featured"]
        lines.append(f"\U0001F3E5 오늘의 기업리뷰: {f['name']} 건강점수 {f['score']:.1f}점")

    lines += [
        "",
        "전 종목 스크리닝 · 재무제표 · 회계감사의견까지, 머니체크업에서 무료로 확인하세요.",
        "\U0001F449 getmoneycheckup.com (프로필 링크 클릭)",
        "",
        "※ 이 게시물은 공개 데이터를 정리한 정보 제공용 콘텐츠이며, 특정 종목에 대한",
        "매수·매도 추천이 아닙니다. 투자 판단과 책임은 본인에게 있습니다.",
        "",
        HASHTAGS,
    ]
    return "\n".join(lines)


WEEKLY_HASHTAGS = ("#국내증시 #코스피 #코스닥 #주간증시 #이번주증시 #주간결산 "
                    "#강세테마 #실적발표 #특징주 #머니체크업 #주식 #주식투자 #국내주식 #재테크")


def build_weekly_caption(data, headline_lines, subtitle):
    """app.py::_weekly_wrap_data()를 공유하는 주간판 캡션 — build_caption()과 같은
    패턴이되 earnings/featured가 없고 gainers가 이미 이름 포함이라 접근 방식이 다름."""
    lines = [" ".join(headline_lines), subtitle, ""]

    if data["gainers"]:
        top = data["gainers"][0]
        lines.append(f"\U0001F4C8 이번주 급등 1위: {top['name']} {top['pct']:+.1f}%")

    if data["anomalies"]:
        lines.append(f"\U0001F6A9 이번주 체크할 이상신호 {len(data['anomalies'])}건")

    if data["strong_themes"]:
        top = data["strong_themes"][0]
        lines.append(f"\U0001F525 이번주 강세 테마: {top['name']} {top['ret_1m']:+.1f}%")

    lines += [
        "",
        "전 종목 스크리닝 · 재무제표 · 회계감사의견까지, 머니체크업에서 무료로 확인하세요.",
        "\U0001F449 getmoneycheckup.com (프로필 링크 클릭)",
        "",
        "※ 이 게시물은 공개 데이터를 정리한 정보 제공용 콘텐츠이며, 특정 종목에 대한",
        "매수·매도 추천이 아닙니다. 투자 판단과 책임은 본인에게 있습니다.",
        "",
        WEEKLY_HASHTAGS,
    ]
    return "\n".join(lines)
