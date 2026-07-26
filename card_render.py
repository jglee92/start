# -*- coding: utf-8 -*-
"""인스타 카드뉴스(캐러셀) 이미지 생성기. app.py::_blog_draft_data()의 구조화 데이터를
그대로 받아 1080x1080 PNG 여러 장을 만든다 — 완성된 텍스트를 다시 파싱하지 않음.

디자인은 사용자가 직접 보여준 레퍼런스(따뜻한 크림/피치 배경 + 스프링노트 카드 +
검정·주황 타이포 + 체크박스 불릿)를 그대로 따르되, "신문 느낌을 가미해달라"는
추가 요청을 반영해 마스트헤드(제호)식 상단 바 + 더블룰(굵은선-얇은선) + 호수/날짜
데이트라인을 얹었다. 제목·큰 숫자는 두 번째 레퍼런스("주요 기업 평균급여" 카드)가
쓴 두꺼운 고딕 스타일(BlackHanSans)로 통일 — 다만 이 폰트는 한글 음절을 일부만
담고 있어 종목명 등 동적 텍스트에서 tofu가 날 수 있으므로 문자열마다 커버리지를
검사해 안 되면 Noto Sans black으로 자동 대체한다(_display_font). 실제 데이터
(종목명·등락률)는 표처럼 좌우 정렬해야 가독성이 나오므로, 레퍼런스의 "중앙 정렬
짧은 문구" 톤은 표지/헤드라인에만 쓰고, 데이터 목록은 좌측 라벨 + 우측 값의 신문
표(box score) 스타일로 변형했다.

이모지는 폰트에 따라 네모(□)로 깨지는 걸 겪어서(Noto CJK류에 컬러이모지 없음)
전부 벡터 도형(체크박스/점/삼각형)으로 대체."""
from __future__ import annotations
import os
import random

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

W = H = 1080


def _rot(seed_key, options):
    """card_templates.py의 표지 헤드라인 로테이션과 같은 패턴 — 섹션 헤드라인도
    매일 문구가 고정이면 AI스러워 보인다는 피드백을 받아, 날짜+슬롯 시드로 문구
    뱅크 중 하나를 고정 선택한다."""
    return random.Random(seed_key).choice(options)

_FONTS_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")
# 본문 폰트는 나눔스퀘어(배포 라이선스가 불명확해 번들 불가) 대신 나눔고딕 사용
# — 사용자 요청. 한글 11,172자 전체를 담고 있어 별도 폴백이 필요 없음.
_BODY_PATHS = {
    "regular": os.path.join(_FONTS_DIR, "NanumGothic-Regular.ttf"),
    "bold": os.path.join(_FONTS_DIR, "NanumGothic-Bold.ttf"),
    "black": os.path.join(_FONTS_DIR, "NanumGothic-ExtraBold.ttf"),
}
_FONT_CACHE = {}


def font(weight, size):
    key = (weight, size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(_BODY_PATHS[weight], size)
    return _FONT_CACHE[key]


# 제목·큰 숫자용 디스플레이 폰트 — 레퍼런스(신문 타이틀 + "1억 8500만원" 스타일 숫자)
# 느낌을 살리려고 씀. 다만 한글 음절을 2,581자(전체 11,172자의 23%)만 담고 있어서
# 종목명·테마명처럼 동적으로 들어오는 텍스트에 쓰면 못 그리는 글자가 네모(tofu)로
# 깨질 위험이 있음 — 그래서 그릴 문자열마다 커버리지를 확인해 안 되면 나눔고딕
# bold로 자동 대체한다(예전에 이모지 깨짐 겪은 뒤로 정착한 안전 패턴과 동일).
#
# "·"(가운뎃점)만 단독으로 빠져 있는데, 이게 "유통·소비재" 같은 흔한 복합어에도
# 나오다 보니 그것 때문에 문자열 전체가 통째로 다른 폰트로 밀려나 버려(카드마다
# 헤드라인 폰트가 들쭉날쭉해 보이는 원인이었음) — 그래서 "·"는 커버리지 검사에서
# 제외하고, 실제로 그릴 때만 _center_display/_draw_display가 직접 점을 그려 넣는다.
FONT_DISPLAY = os.path.join(_FONTS_DIR, "BlackHanSans-Regular.ttf")
_DISPLAY_CMAP = set(TTFont(FONT_DISPLAY).getBestCmap().keys())
_DISPLAY_CACHE = {}
_MIDDOT = "·"


def _covers(text):
    return all(ch == _MIDDOT or ord(ch) in _DISPLAY_CMAP or ch.isspace() for ch in text)


def _display_font(text, size):
    if not _covers(text):
        return font("bold", size)
    if size not in _DISPLAY_CACHE:
        _DISPLAY_CACHE[size] = ImageFont.truetype(FONT_DISPLAY, size)
    return _DISPLAY_CACHE[size]


def _draw_display(d, text, size, x, y, color):
    """_display_font로 그리되 "·"는 수동으로 작은 점을 찍어 대체. 왼쪽 정렬,
    그린 전체 너비를 반환."""
    fnt = _display_font(text, size)
    parts = text.split(_MIDDOT)
    gap = size * 0.38
    dot_d = max(4, size * 0.09)
    cx = x
    for i, part in enumerate(parts):
        if part:
            d.text((cx, y), part, font=fnt, fill=color)
            cx += d.textlength(part, font=fnt)
        if i < len(parts) - 1:
            dot_cy = y + size * 0.62
            cx += gap / 2
            d.ellipse([cx - dot_d / 2, dot_cy - dot_d / 2, cx + dot_d / 2, dot_cy + dot_d / 2], fill=color)
            cx += gap / 2
    return cx - x


def _center_display(d, text, size, cx, y, color):
    """가운데 정렬 버전 — 전체 너비를 먼저 재서 중앙에 맞춘 뒤 _draw_display로 그림."""
    fnt = _display_font(text, size)
    parts = text.split(_MIDDOT)
    gap = size * 0.38
    total = sum(d.textlength(p, font=fnt) for p in parts) + gap * (len(parts) - 1)
    return _draw_display(d, text, size, cx - total / 2, y, color)


# --- 팔레트: 레퍼런스의 따뜻한 크림/피치 + 신문 잉크 블랙 + 브랜드 오렌지 ---
BG_PEACH = (250, 224, 193)
CARD_BG = (255, 252, 246)         # 신문지에 가까운 아이보리(순백보다 따뜻함)
CARD_SHADOW = (232, 190, 145)     # 노트 뒷장처럼 살짝 어두운 피치
CARD_BORDER = (223, 201, 176)
RING = (32, 27, 23)               # 스프링 링 윤곽선
INK = (26, 22, 19)                # 헤드라인 잉크(순검정보다 부드러움)
INK_SOFT = (104, 92, 80)          # 본문 회갈색
DIM = (156, 141, 123)             # 캡션/푸터
RULE = (214, 194, 170)            # 얇은 구분선
ORANGE = (224, 106, 43)           # 브랜드 강조(레퍼런스 대비 살짝 차분하게)
GOOD = (35, 194, 129)
BAD = (214, 62, 58)


def _bg():
    return Image.new("RGB", (W, H), BG_PEACH)


CARD = (72, 176, 1008, 976)  # x0, y0, x1, y1


def _notepad_card():
    """레퍼런스의 스프링노트 카드: 뒤에 살짝 어긋난 그림자 시트 + 흰 카드 + 상단
    스프링 링(윤곽선만 그려서 뒤 배경/카드 색이 링 구멍 사이로 비치게 함)."""
    img = _bg()
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = CARD
    off = 16
    d.rounded_rectangle([x0 + off, y0 + off, x1 + off, y1 + off], radius=36, fill=CARD_SHADOW)
    d.rounded_rectangle([x0, y0, x1, y1], radius=36, fill=CARD_BG, outline=CARD_BORDER, width=2)

    ring_w, n, inset = 26, 13, 62
    step = ((x1 - inset) - (x0 + inset)) / (n - 1)
    for i in range(n):
        rx = x0 + inset + i * step
        d.rounded_rectangle([rx - ring_w / 2, y0 - 34, rx + ring_w / 2, y0 + 26],
                             radius=ring_w / 2, outline=RING, width=5)
    return img, d


def _wrap(draw, text, fnt, max_w):
    lines, cur = [], ""
    for ch in text:
        test = cur + ch
        if draw.textlength(test, font=fnt) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def _center_text(d, text, fnt, cx, y, fill):
    w = d.textlength(text, font=fnt)
    d.text((cx - w / 2, y), text, font=fnt, fill=fill)
    return w


ICON_PATH = os.path.join(os.path.dirname(__file__), "static", "icon-512.png")
_ICON_CACHE = {}


def _load_icon(size):
    if size not in _ICON_CACHE:
        icon = Image.open(ICON_PATH).convert("RGBA")
        icon = icon.crop(icon.getbbox())
        scale = size / max(icon.size)
        icon = icon.resize((max(1, int(icon.width * scale)), max(1, int(icon.height * scale))),
                            Image.LANCZOS)
        _ICON_CACHE[size] = icon
    return _ICON_CACHE[size]


def _masthead(img, d, x0, x1, y, section_label, dateline):
    """신문 제호 바 — 굵은 룰 + 섹션명(좌) + 데이트라인(우) + 얇은 룰(더블룰)."""
    d.line([(x0, y), (x1, y)], fill=INK, width=4)
    y += 12
    d.text((x0, y), section_label.upper(), font=font("bold", 20), fill=ORANGE)
    dw = d.textlength(dateline, font=font("regular", 18))
    d.text((x1 - dw, y + 2), dateline, font=font("regular", 18), fill=DIM)
    y += 34
    d.line([(x0, y), (x1, y)], fill=RULE, width=2)
    return y + 30


def _checkbox(d, x, y, size=24, color=ORANGE):
    d.rounded_rectangle([x, y, x + size, y + size], radius=5, outline=color, width=4)
    d.line([(x + size * 0.22, y + size * 0.52), (x + size * 0.42, y + size * 0.74),
            (x + size * 0.82, y + size * 0.26)], fill=color, width=4, joint="curve")


def _cta_box(d, ex, ey, y, title, height=118):
    """마지막 장(오늘의 기업리뷰) 클로징 CTA — 예전엔 주도테마 카드에 있었는데
    캐러셀을 5장으로 줄이며 진짜 마지막 액션이 되도록 이 장으로 옮겨왔다."""
    d.rounded_rectangle([ex, y, ey, y + height], radius=18, outline=ORANGE, width=3)
    _checkbox(d, ex + 22, y + 18, size=24)
    d.text((ex + 58, y + 14), title, font=_display_font(title, 24), fill=INK)
    d.text((ex + 58, y + 50), "재무제표 · 회계감사의견까지 한번에", font=font("regular", 17), fill=DIM)
    d.text((ex + 22, y + 80), "getmoneycheckup.com", font=font("bold", 23), fill=ORANGE)


def _footer(img, d, x0, x1, y1, date_str, page, total):
    cx = (x0 + x1) // 2
    txt = f"머니체크업 · {date_str} · {page:02d}/{total:02d}"
    fnt = font("regular", 18)
    tw = d.textlength(txt, font=fnt)
    icon = _load_icon(22)
    start_x = cx - (icon.width + 8 + tw) / 2
    img.paste(icon, (int(start_x), int(y1 - 54)), icon)
    d.text((start_x + icon.width + 8, y1 - 52), txt, font=fnt, fill=DIM)


def _row(d, x0, x1, y, label, value=None, value_color=None, dot_color=None,
         label_font=None, value_font=None):
    """좌측 점불릿+라벨, 우측 값 — 신문 박스스코어(box score) 표 한 줄."""
    label_font = label_font or font("regular", 27)
    value_font = value_font or font("bold", 28)
    if dot_color:
        d.ellipse([x0, y + 10, x0 + 14, y + 24], fill=dot_color)
        d.text((x0 + 26, y), label, font=label_font, fill=INK)
    else:
        d.text((x0, y), label, font=label_font, fill=INK)
    if value is not None:
        vw = d.textlength(value, font=value_font)
        d.text((x1 - vw, y), value, font=value_font, fill=value_color or INK)


def _pct_text(v):
    return f"{v:+.1f}%"


def _sign_color(v):
    return GOOD if v is not None and v >= 0 else BAD


def _grade_color(label):
    """4차원 등급 라벨(factor/interpret.py::LABELS)을 색으로 — 개별 항목마다 다른
    색을 주기보다, 등급 자체의 좋고 나쁨을 의미하는 색으로 통일(기존 초록=좋음/
    빨강=주의 관례를 그대로 따름)."""
    if label in ("매우 우수", "우수"):
        return GOOD
    if label in ("미흡", "부족"):
        return BAD
    return DIM  # 보통 / 데이터 없음


def _dim_box(d, x, y, w, h, label, dim):
    """기업 종합검진 4차원(밸류에이션/수익성/안정성/성장성) 박스 하나 — 라벨+별점
    한 줄, 등급 텍스트 한 줄, 설명 문장(줄바꿈)."""
    d.rounded_rectangle([x, y, x + w, y + h], radius=16, outline=RULE, width=2)
    pad = 20
    tx, ty = x + pad, y + pad
    d.text((tx, ty), label, font=font("bold", 21), fill=INK)

    stars = dim["stars"] or 0
    star_fnt = font("bold", 19)
    filled, empty = "★" * stars, "☆" * (5 - stars)
    ew = d.textlength(empty, font=star_fnt)
    fw = d.textlength(filled, font=star_fnt)
    ex_ = x + w - pad - ew
    d.text((ex_ - fw, ty + 2), filled, font=star_fnt, fill=ORANGE)
    d.text((ex_, ty + 2), empty, font=star_fnt, fill=RULE)

    ty += 36
    d.text((tx, ty), dim["label"], font=font("bold", 18), fill=_grade_color(dim["label"]))
    ty += 30
    for line in _wrap(d, dim["text"], font("regular", 17), w - pad * 2)[:4]:
        d.text((tx, ty), line, font=font("regular", 17), fill=INK_SOFT)
        ty += 24


# ---------------- 카드별 렌더 ----------------

def pick_cover_highlights(data, name_of):
    """표지 카드 하단에 보여줄 '오늘 한눈에 보기' 스탯 3~4개를 우선순위로 고른다.
    사용자 요청 — 표지가 헤드라인 하나로 스와이프를 유도하는 대신, 오늘의 핵심 숫자를
    한 장에서 바로 보여주자는 컨셉(레퍼런스 이미지의 '요약 먼저' 구조는 차용하되, 비주얼은
    우리 신문 노트패드 톤 그대로 유지 — 캐릭터 일러스트 없이 데이터만으로 임팩트).
    이미 _blog_draft_data()에 있는 값만 써서 새 데이터 수집은 필요 없다."""
    picks = []
    ix = data.get("us_indices") or {}
    kospi = ix.get("kospi")
    if kospi and kospi.get("chg_pct") is not None:
        picks.append(("코스피", f"{kospi['chg_pct']:+.1f}%", _sign_color(kospi["chg_pct"])))
    if data.get("gainers"):
        code, pct = data["gainers"][0]
        picks.append((name_of(code), f"{pct:+.1f}%", GOOD))
    if data.get("themes"):
        top = data["themes"][0]
        picks.append((top["mid"], f"{top['ret_1m']:+.1f}%", _sign_color(top["ret_1m"])))
    if data.get("anomalies"):
        picks.append(("이상신호", f"{len(data['anomalies'])}건", BAD))
    elif data.get("earnings"):
        n_s = sum(1 for e in data["earnings"] if e["tag"] == "surprise")
        if n_s:
            picks.append(("어닝서프라이즈", f"{n_s}건", GOOD))
    return picks[:4]


def _highlight_row(d, x0, x1, y, highlights):
    """스탯 박스 가로 배열 — 라벨(업종·종목명 등)은 길 수 있어 2줄까지 접는다."""
    n = len(highlights)
    gap = 16
    box_w = (x1 - x0 - gap * (n - 1)) / n
    box_h = 128
    for i, (label, value, color) in enumerate(highlights):
        bx = x0 + i * (box_w + gap)
        d.rounded_rectangle([bx, y, bx + box_w, y + box_h], radius=14, outline=RULE, width=2)
        pad = 16
        ly = y + 14
        for line in _wrap(d, label, font("regular", 17), box_w - pad * 2)[:2]:
            d.text((bx + pad, ly), line, font=font("regular", 17), fill=DIM)
            ly += 22
        vfont = _display_font(value, 30)
        d.text((bx + pad, y + box_h - 46), value, font=vfont, fill=color)


def _headline_size(text, base=62, ref_len=9, per_char=2.2, min_size=50):
    """글자 수가 적은 줄은 같은 크기라도 더 크고 진하게 보이는 착시가 있어서
    (예: 오렌지색 7자 줄이 검정색 9자 줄보다 두드러져 보임 — 실제 사용자 스크린샷
    피드백으로 발견) 기준 길이(ref_len)보다 짧으면 그만큼 살짝 줄인다. 너무 작아지진
    않게 하한(min_size)을 둔다."""
    n = len(text)
    if n >= ref_len:
        return base
    return max(min_size, round(base - (ref_len - n) * per_char))


def render_cover(headline_lines, subtitle, date_str, page, total,
                  section_label="장전 브리핑", dateline_suffix="오늘의 한 장", highlights=None):
    img, d = _notepad_card()
    x0, y0, x1, y1 = CARD
    cx = (x0 + x1) // 2
    ex, ey = x0 + 56, x1 - 56
    y = _masthead(img, d, ex, ey, y0 + 46, section_label, f"{date_str} · {dateline_suffix}")

    y += 90
    n = len(headline_lines)
    for i, line in enumerate(headline_lines):
        color = ORANGE if i == n - 1 else INK
        _center_display(d, line, _headline_size(line), cx, y, color)
        y += 76
    y += 18
    d.line([(cx - 60, y), (cx + 60, y)], fill=RULE, width=3)
    y += 36
    if subtitle:
        for line in _wrap(d, subtitle, font("bold", 26), x1 - x0 - 200)[:2]:
            _center_display(d, line, 26, cx, y, INK_SOFT)
            y += 38

    if highlights:
        y += 34
        _draw_display(d, "오늘 한눈에 보기", 24, ex, y, INK)
        y += 44
        _highlight_row(d, ex, ey, y, highlights)

    _footer(img, d, x0, x1, y1, date_str, page, total)
    return img


def render_market(data, date_str, page, total, section_no):
    img, d = _notepad_card()
    x0, y0, x1, y1 = CARD
    cx = (x0 + x1) // 2
    ix = data["us_indices"] or {}
    nasdaq_up = ix.get("nasdaq", {}).get("chg_pct", 0) >= 0
    headline = _rot(f"{date_str}|market", [
        "미국은 웃었고, 환율은 올랐다", "간밤 뉴욕은 강세, 환율도 들썩",
        "미국 증시 훈풍, 오늘 환율은?",
    ]) if nasdaq_up else _rot(f"{date_str}|market", [
        "미국도 조심스럽고, 환율도 흔들렸다", "간밤 뉴욕은 약세, 환율도 출렁",
        "미국 증시 주춤, 오늘 환율은?",
    ])

    y = _masthead(img, d, x0 + 56, x1 - 56, y0 + 46, f"{section_no:02d} · 간밤 시장", f"{date_str}")
    _center_display(d, headline, 38, cx, y, INK)
    y += 66

    ex, ey = x0 + 56, x1 - 56
    cols = [("nasdaq", "나스닥"), ("sp500", "S&P 500"), ("usdkrw", "원달러")]
    col_w = (ey - ex) / 3
    d.line([(ex, y), (ey, y)], fill=RULE, width=2)
    y += 26
    for i, (key, label) in enumerate(cols):
        v = ix.get(key)
        x = ex + i * col_w
        d.text((x, y), label, font=font("regular", 20), fill=DIM)
        if v and key != "usdkrw" and v.get("chg_pct") is not None:
            txt, color = _pct_text(v["chg_pct"]), _sign_color(v["chg_pct"])
        elif v and key == "usdkrw" and v.get("price"):
            txt, color = f"{v['price']:,.1f}원", INK
        else:
            txt, color = "-", DIM
        d.text((x, y + 30), txt, font=_display_font(txt, 32), fill=color)
        if i > 0:
            d.line([(x - 4, y - 4), (x - 4, y + 74)], fill=RULE, width=1)
    y += 110
    d.line([(ex, y), (ey, y)], fill=RULE, width=2)
    y += 34

    if data["movers_date"]:
        mv_label = f"어제({data['movers_date'][5:].replace('-', '.')}) 급등·급락 TOP3"
        _draw_display(d, mv_label, 25, ex, y, INK)
        y += 46
        half = (ey - ex) / 2 - 20
        from itertools import zip_longest
        ry = y
        for gainer, loser in zip_longest(data["gainers"], data["losers"]):
            if gainer:
                gv = _pct_text(gainer[1])
                _row(d, ex, ex + half, ry, data["_name_of"](gainer[0]), gv,
                     value_color=GOOD, dot_color=GOOD, label_font=font("regular", 24),
                     value_font=_display_font(gv, 26))
            if loser:
                lv = _pct_text(loser[1])
                _row(d, ex + half + 40, ey, ry, data["_name_of"](loser[0]), lv,
                     value_color=BAD, dot_color=BAD, label_font=font("regular", 24),
                     value_font=_display_font(lv, 26))
            ry += 50
        d.line([(ex + half + 20, y - 10), (ex + half + 20, ry - 20)], fill=RULE, width=1)

    _footer(img, d, x0, x1, y1, date_str, page, total)
    return img


_ANOMALY_HEADLINES = {
    "적자 전환": ["흑자에서 적자로 전환", "이 회사들, 적자로 돌아섰다", "흑자였던 곳이 적자로"],
    "비적정 감사의견": ["감사의견, 적정 아님", "감사인이 문제를 제기했다"],
    "영업외 손익 의존": ["영업이익 적자인데 순이익만 흑자", "본업 말고 다른 데서 번 이익"],
    "부채비율 급증": ["부채비율이 급격히 늘었다", "빚이 갑자기 늘어난 곳들"],
    "매출": ["매출이 계속 줄고 있다", "매출 감소가 이어지는 곳들"],
}
_ANOMALY_FALLBACK = ["조심해서 봐야 할 재무 신호", "오늘 체크할 위험 신호"]
_SIGNALS_HEADLINES_BOTH = [
    "오늘의 종목 시그널", "실적으로 웃고, 신호로 울고",
    "오늘 체크할 종목들", "실적부터 위험신호까지, 한 장 정리",
]


def _signals_headline(data, seed):
    """실적·이상신호를 한 장에 합친 카드 헤드라인 — 둘 다 있으면 공용 문구,
    한쪽만 있으면 그쪽 성격에 맞는 문구를 쓴다."""
    has_earnings, anomalies = bool(data["earnings"]), data["anomalies"]
    if has_earnings and anomalies:
        return _rot(f"{seed}|signals", _SIGNALS_HEADLINES_BOTH)
    if anomalies:
        label = anomalies[0]["label"]
        for key, options in _ANOMALY_HEADLINES.items():
            if key in label:
                return _rot(f"{seed}|{key}", options)
        return _rot(f"{seed}|fallback", _ANOMALY_FALLBACK)
    return _rot(f"{seed}|earnings", [
        "누가 웃고, 누가 울었나", "오늘 실적표, 희비가 갈렸다", "숫자로 보는 오늘의 실적",
    ])


def render_signals(data, date_str, page, total, section_no):
    """실적 서프라이즈·쇼크 + 재무 위험신호를 한 장으로 합친 카드 — 예전엔 두 장으로
    나뉘어 있었는데 둘 다 '개별 종목 시그널'이라 성격이 겹치고, 6장이던 캐러셀을
    5장으로 줄여달라는 요청에 따라 합쳤다."""
    img, d = _notepad_card()
    x0, y0, x1, y1 = CARD
    cx = (x0 + x1) // 2
    ex, ey = x0 + 56, x1 - 56
    y = _masthead(img, d, ex, ey, y0 + 46, f"{section_no:02d} · 종목 시그널", f"{date_str}")
    headline = _signals_headline(data, date_str)
    _center_display(d, headline, 34, cx, y, INK)
    y += 66

    surprises = [e for e in data["earnings"] if e["tag"] == "surprise"][:2]
    shocks = [e for e in data["earnings"] if e["tag"] == "shock"][:1]

    if surprises:
        d.text((ex, y), "어닝 서프라이즈", font=_display_font("어닝 서프라이즈", 22), fill=GOOD)
        y += 38
        for e in surprises:
            v = f"순이익 {_pct_text(e['ni_yoy'])}"
            _row(d, ex, ey, y, e["name"], v, value_color=GOOD, dot_color=GOOD,
                 label_font=font("regular", 25), value_font=_display_font(v, 26))
            y += 46
        y += 16

    if shocks:
        d.text((ex, y), "어닝 쇼크", font=_display_font("어닝 쇼크", 22), fill=BAD)
        y += 38
        for e in shocks:
            v = f"순이익 {_pct_text(e['ni_yoy'])}"
            _row(d, ex, ey, y, e["name"], v, value_color=BAD, dot_color=BAD,
                 label_font=font("regular", 25), value_font=_display_font(v, 26))
            y += 38
            if e.get("rev_yoy") is not None:
                d.text((ex + 26, y), f"매출 {_pct_text(e['rev_yoy'])}", font=font("regular", 18), fill=DIM)
                y += 28
        y += 16

    if data["anomalies"]:
        d.text((ex, y), "위험 신호", font=_display_font("위험 신호", 22), fill=BAD)
        y += 38
        for a in data["anomalies"][:3]:
            cyc = y + 13
            d.ellipse([ex, cyc - 13, ex + 26, cyc + 13], outline=BAD, width=3)
            d.line([(ex + 13, cyc - 5), (ex + 13, cyc + 3)], fill=BAD, width=3)
            d.ellipse([ex + 11.5, cyc + 6, ex + 14.5, cyc + 9], fill=BAD)
            row_txt = f"{a['name']} ({a['code']})"
            d.text((ex + 40, y), row_txt, font=_display_font(row_txt, 25), fill=INK)
            y += 50

    _footer(img, d, x0, x1, y1, date_str, page, total)
    return img


def render_theme(data, date_str, page, total, section_no):
    img, d = _notepad_card()
    x0, y0, x1, y1 = CARD
    cx = (x0 + x1) // 2
    ex, ey = x0 + 56, x1 - 56
    themes = data["themes"]
    top = themes[0] if themes else None
    if top:
        sign = "+" if top["ret_1m"] >= 0 else ""
        headline = _rot(f"{date_str}|theme", [
            f"{top['mid']} 한 달 새 {sign}{top['ret_1m']:.1f}%",
            f"요즘 뜨는 테마, {top['mid']}",
            f"{top['mid']}, 최근 한 달 {sign}{top['ret_1m']:.1f}%",
        ])
    else:
        headline = _rot(f"{date_str}|theme_none", [
            "요즘 주도테마 한눈에 보기", "지금 이 테마들이 뜬다",
        ])

    y = _masthead(img, d, ex, ey, y0 + 46, f"{section_no:02d} · 주도테마", f"{date_str}")
    _center_display(d, headline, 34, cx, y, INK)
    y += 70

    for m in themes[:4]:
        tv = _pct_text(m["ret_1m"])
        _row(d, ex, ey, y, m["mid"], tv, value_color=_sign_color(m["ret_1m"]),
             label_font=font("regular", 27), value_font=_display_font(tv, 28))
        y += 40

        # 테마명만 나열하면 와닿지 않는다는 피드백 — 대표 세부테마의 예시 종목을
        # 바로 아래에 붙인다(블로그 글엔 이미 쓰던 데이터, 카드엔 안 옮겨져 있었음).
        examples = next((s["examples"] for s in m.get("sub", []) if s.get("examples")), None)
        if examples:
            d.text((ex, y), f"예: {', '.join(examples[:3])}", font=font("regular", 20), fill=DIM)
            y += 32
        y += 12
        d.line([(ex, y - 8), (ey, y - 8)], fill=RULE, width=1)
        y += 6

    _footer(img, d, x0, x1, y1, date_str, page, total)
    return img


_DIM_ORDER = [("value", "밸류에이션"), ("profit", "수익성"), ("safety", "안정성"), ("growth", "성장성")]


def render_company_review(data, date_str, page, total, section_no):
    """마지막 장 — '오늘의 기업리뷰'. 랭킹 1~20위를 영업일마다 하나씩 순서대로 보여줘
    (app.py::_company_of_the_day) 전 종목 스크리닝·회계감사의견까지 보여준다는 우리
    강점을 매일 실제 종목 하나로 직접 증명하는 클로징 카드."""
    img, d = _notepad_card()
    x0, y0, x1, y1 = CARD
    cx = (x0 + x1) // 2
    ex, ey = x0 + 56, x1 - 56
    y = _masthead(img, d, ex, ey, y0 + 46, f"{section_no:02d} · 오늘의 기업리뷰", f"{date_str}")

    f = data.get("featured")
    if not f:
        _center_display(d, "오늘의 기업리뷰 준비 중", 34, cx, y + 80, INK)
        _cta_box(d, ex, ey, y1 - 190, "전 종목 스크리닝, 무료로")
        _footer(img, d, x0, x1, y1, date_str, page, total)
        return img

    # "종합랭킹 N위"로 쓰면 매수 추천 순위처럼 오해할 수 있어(사용자 피드백) —
    # 헤드라인은 건강검진 결과처럼 읽히는 점수를 앞세우고, 등수는 부제목에 참고용으로만.
    headline = f"{f['name']} 건강점수 {f['score']:.1f}점"
    _center_display(d, headline, 36, cx, y, INK)
    y += 50
    _center_text(d, f"{f['code']} · 건강점수 랭킹 {f['rank']}위(참고용)", font("regular", 20), cx, y, DIM)
    y += 40

    # CTA(전 종목 스크리닝 안내)를 이 마지막 장으로 옮겨오면서(예전엔 주도테마 카드에
    # 있었음 — 6장→5장으로 줄이며 캐러셀의 진짜 마지막 액션이 되도록 재배치) 박스
    # 높이를 살짝 줄여 공간을 만들었다.
    dims = f["dims"]
    box_w = (ey - ex - 20) / 2
    box_h = 178
    for i, (key, label) in enumerate(_DIM_ORDER):
        bx = ex + (i % 2) * (box_w + 20)
        by = y + (i // 2) * (box_h + 20)
        _dim_box(d, bx, by, box_w, box_h, label, dims[key])
    y += 2 * box_h + 20 + 22

    _cta_box(d, ex, ey, y, "전 종목 스크리닝, 무료로")

    _footer(img, d, x0, x1, y1, date_str, page, total)
    return img


# ---------------- 주간 리포트(토요일) 카드 ----------------
# app.py::_weekly_wrap_data() 구조화 데이터 기반 — 일간 카드와 섹션 구성은 비슷하되
# (표지→시황→시그널→테마) 데이터 키가 달라(gainers/losers가 이미 이름 포함,
# earnings 없음, us_indices 대신 idx) 별도 렌더 함수로 둔다. 오늘의 기업리뷰는
# 주간 데이터에 대응하는 게 없어 생략하고, CTA는 마지막 장인 테마 카드로 옮겼다.

def render_weekly_market(data, date_str, page, total, section_no):
    img, d = _notepad_card()
    x0, y0, x1, y1 = CARD
    cx = (x0 + x1) // 2
    ex, ey = x0 + 56, x1 - 56

    idx = data["idx"]
    if idx:
        top = max(idx, key=lambda i: abs(i["chg"]))
        mood = "상승" if top["chg"] >= 0 else "하락"
        headline = _rot(f"{date_str}|wk_market", [
            f"{top['name']} 이번주 {mood} 마감", "이번주 국내증시 결산",
        ])
    else:
        headline = "이번주 국내증시 결산"

    y = _masthead(img, d, ex, ey, y0 + 46, f"{section_no:02d} · 이번주 시황", f"{date_str}")
    _center_display(d, headline, 36, cx, y, INK)
    y += 66

    if idx:
        col_w = (ey - ex) / len(idx)
        d.line([(ex, y), (ey, y)], fill=RULE, width=2)
        y += 26
        for i, item in enumerate(idx):
            x = ex + i * col_w
            d.text((x, y), item["name"], font=font("regular", 22), fill=DIM)
            txt = _pct_text(item["chg"])
            d.text((x, y + 32), txt, font=_display_font(txt, 34), fill=_sign_color(item["chg"]))
            if i > 0:
                d.line([(x - 4, y - 4), (x - 4, y + 78)], fill=RULE, width=1)
        y += 114
        d.line([(ex, y), (ey, y)], fill=RULE, width=2)
        y += 34

    if data["gainers"] or data["losers"]:
        _draw_display(d, "금주 급등·급락 TOP3", 25, ex, y, INK)
        y += 46
        half = (ey - ex) / 2 - 20
        from itertools import zip_longest
        ry = y
        for gainer, loser in zip_longest(data["gainers"], data["losers"]):
            if gainer:
                gv = _pct_text(gainer["pct"])
                _row(d, ex, ex + half, ry, gainer["name"], gv,
                     value_color=GOOD, dot_color=GOOD, label_font=font("regular", 24),
                     value_font=_display_font(gv, 26))
            if loser:
                lv = _pct_text(loser["pct"])
                _row(d, ex + half + 40, ey, ry, loser["name"], lv,
                     value_color=BAD, dot_color=BAD, label_font=font("regular", 24),
                     value_font=_display_font(lv, 26))
            ry += 50
        d.line([(ex + half + 20, y - 10), (ex + half + 20, ry - 20)], fill=RULE, width=1)

    _footer(img, d, x0, x1, y1, date_str, page, total)
    return img


def render_weekly_signals(data, date_str, page, total, section_no):
    """이상신호 + 종합점수 급상승·급하락 종목을 한 장으로(일간의 실적 자리를 주간엔
    점수 변동으로 대체 — 주간 데이터엔 최근 공시 실적이 따로 없음)."""
    img, d = _notepad_card()
    x0, y0, x1, y1 = CARD
    cx = (x0 + x1) // 2
    ex, ey = x0 + 56, x1 - 56
    y = _masthead(img, d, ex, ey, y0 + 46, f"{section_no:02d} · 이번주 체크포인트", f"{date_str}")
    headline = _rot(f"{date_str}|wk_signals", [
        "이번주 체크할 종목들", "이번주 점수가 갈린 종목", "한 주간 달라진 것들",
    ])
    _center_display(d, headline, 34, cx, y, INK)
    y += 66

    if data["anomalies"]:
        d.text((ex, y), "위험 신호", font=_display_font("위험 신호", 22), fill=BAD)
        y += 38
        for a in data["anomalies"][:3]:
            cyc = y + 13
            d.ellipse([ex, cyc - 13, ex + 26, cyc + 13], outline=BAD, width=3)
            d.line([(ex + 13, cyc - 5), (ex + 13, cyc + 3)], fill=BAD, width=3)
            d.ellipse([ex + 11.5, cyc + 6, ex + 14.5, cyc + 9], fill=BAD)
            row_txt = f"{a['name']} ({a['code']})"
            d.text((ex + 40, y), row_txt, font=_display_font(row_txt, 25), fill=INK)
            y += 50
        y += 10

    score_up = data["score_up"][:2]
    if score_up:
        d.text((ex, y), "점수 급상승", font=_display_font("점수 급상승", 22), fill=GOOD)
        y += 38
        for m in score_up:
            v = f"{m['score']:.1f}점 ({m['score_change']:+.1f})"
            _row(d, ex, ey, y, m["name"], v, value_color=GOOD, dot_color=GOOD,
                 label_font=font("regular", 24), value_font=_display_font(v, 24))
            y += 44
        y += 10

    score_down = data["score_down"][:2]
    if score_down:
        d.text((ex, y), "점수 급하락", font=_display_font("점수 급하락", 22), fill=BAD)
        y += 38
        for m in score_down:
            v = f"{m['score']:.1f}점 ({m['score_change']:+.1f})"
            _row(d, ex, ey, y, m["name"], v, value_color=BAD, dot_color=BAD,
                 label_font=font("regular", 24), value_font=_display_font(v, 24))
            y += 44

    _footer(img, d, x0, x1, y1, date_str, page, total)
    return img


def render_weekly_theme(data, date_str, page, total, section_no):
    """이번주 강세 테마 TOP5 + CTA — 주간 카드엔 '오늘의 기업리뷰'에 대응하는 게
    없어(랭킹 로테이션은 일간 개념) 마지막 장인 이 카드로 CTA를 가져왔다."""
    img, d = _notepad_card()
    x0, y0, x1, y1 = CARD
    cx = (x0 + x1) // 2
    ex, ey = x0 + 56, x1 - 56
    themes = data["strong_themes"]
    top = themes[0] if themes else None
    if top:
        sign = "+" if top["ret_1m"] >= 0 else ""
        headline = _rot(f"{date_str}|wk_theme", [
            f"이번주 최고 테마, {top['name']}", f"{top['name']} 이번주 {sign}{top['ret_1m']:.1f}%",
        ])
    else:
        headline = "이번주 강세 테마 TOP5"

    y = _masthead(img, d, ex, ey, y0 + 46, f"{section_no:02d} · 이번주 강세테마", f"{date_str}")
    _center_display(d, headline, 34, cx, y, INK)
    y += 70

    for t in themes[:4]:
        tv = _pct_text(t["ret_1m"])
        _row(d, ex, ey, y, t["name"], tv, value_color=_sign_color(t["ret_1m"]),
             label_font=font("regular", 26), value_font=_display_font(tv, 27))
        y += 38
        if t.get("examples"):
            d.text((ex, y), f"예: {', '.join(t['examples'][:3])}", font=font("regular", 19), fill=DIM)
            y += 30
        y += 10
        d.line([(ex, y - 6), (ey, y - 6)], fill=RULE, width=1)
        y += 8

    # CTA는 고정 위치가 아니라 방금 그린 테마 목록 바로 아래(콘텐츠가 적은 주엔 위로
    # 붙고, 4개 꽉 찬 주엔 아래로 내려가되 항상 푸터 위 여유 공간을 확보).
    _cta_box(d, ex, ey, min(y + 16, y1 - 190), "전 종목 스크리닝, 무료로")

    _footer(img, d, x0, x1, y1, date_str, page, total)
    return img


def generate_weekly_cards(data, headline_lines, subtitle, date_str, out_dir="cards_out"):
    """data: app.py::_weekly_wrap_data() 결과. generate_cards()의 주간판 — 섹션이
    유동적으로 빠지는 로직은 동일(예: 이상신호·점수변동이 전부 없는 주는 시그널
    카드 생략)."""
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith(".png"):
            os.remove(os.path.join(out_dir, f))

    sections = ["market"]
    if data["anomalies"] or data["score_up"] or data["score_down"]:
        sections.append("signals")
    sections.append("theme")  # 마지막 장 — CTA 포함, 항상 존재

    total = 1 + len(sections)
    paths = []

    cover = render_cover(headline_lines, subtitle, date_str, 1, total,
                         section_label="주간 마무리", dateline_suffix="이번주 한 장 요약")
    p = os.path.join(out_dir, "01.png")
    cover.save(p)
    paths.append(p)

    section_no = 1
    for i, kind in enumerate(sections, start=2):
        if kind == "market":
            img = render_weekly_market(data, date_str, i, total, section_no)
        elif kind == "signals":
            img = render_weekly_signals(data, date_str, i, total, section_no)
        elif kind == "theme":
            img = render_weekly_theme(data, date_str, i, total, section_no)
        p = os.path.join(out_dir, f"{i:02d}.png")
        img.save(p)
        paths.append(p)
        section_no += 1

    return paths


def generate_cards(data, name_of, headline_lines, subtitle, date_str, out_dir="cards_out"):
    """data: app.py::_blog_draft_data() 결과. 섹션이 없는 날은 그 카드를 건너뛰어
    장수가 유동적으로 줄어든다(예: 실적발표 없는 날 실적 카드 생략)."""
    data = dict(data)
    data["_name_of"] = name_of
    os.makedirs(out_dir, exist_ok=True)
    # 카드 장수가 어제보다 줄어든 날(예: 이상신호 없는 날) 이전 실행의 여분 PNG가
    # 그대로 남아있으면 캐러셀에 옛날 카드까지 같이 올라갈 수 있어(post_to_instagram.py가
    # 폴더 안 .png 전부를 줍기 때문) — 새로 만들기 전에 이전 산출물을 지운다.
    for f in os.listdir(out_dir):
        if f.endswith(".png"):
            os.remove(os.path.join(out_dir, f))

    sections = []
    if data["us_indices"] or data["gainers"] or data["losers"]:
        sections.append("market")
    # 실적(어닝서프라이즈·쇼크)과 이상신호는 둘 다 '개별 종목 시그널'이라 한 장으로
    # 합침(6장→5장 요청) — 둘 중 하나라도 있으면 카드 자체는 추가.
    if data["earnings"] or data["anomalies"]:
        sections.append("signals")
    sections.append("theme")
    # 오늘의 기업리뷰(랭킹 1~50위 로테이션 + CTA)는 항상 맨 마지막 장으로 마무리.
    sections.append("company_review")

    total = 1 + len(sections)  # 총 장수를 렌더링 전에 먼저 확정(페이지 번호 불일치 방지)
    paths = []

    highlights = pick_cover_highlights(data, name_of)
    cover = render_cover(headline_lines, subtitle, date_str, 1, total, highlights=highlights)
    p = os.path.join(out_dir, "01.png")
    cover.save(p)
    paths.append(p)

    section_no = 1
    for i, kind in enumerate(sections, start=2):
        if kind == "market":
            img = render_market(data, date_str, i, total, section_no)
        elif kind == "signals":
            img = render_signals(data, date_str, i, total, section_no)
        elif kind == "theme":
            img = render_theme(data, date_str, i, total, section_no)
        elif kind == "company_review":
            img = render_company_review(data, date_str, i, total, section_no)
        p = os.path.join(out_dir, f"{i:02d}.png")
        img.save(p)
        paths.append(p)
        section_no += 1

    return paths
