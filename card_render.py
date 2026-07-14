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

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

W = H = 1080

_FONTS_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")
FONT_SANS = os.path.join(_FONTS_DIR, "NotoSansKR-VF.ttf")
_SANS_WEIGHTS = {"light": 300, "regular": 400, "bold": 700, "black": 900}
_FONT_CACHE = {}


def font(weight, size):
    key = (weight, size)
    if key not in _FONT_CACHE:
        f = ImageFont.truetype(FONT_SANS, size)
        f.set_variation_by_axes([_SANS_WEIGHTS[weight]])
        _FONT_CACHE[key] = f
    return _FONT_CACHE[key]


# 제목·큰 숫자용 디스플레이 폰트 — 레퍼런스(신문 타이틀 + "1억 8500만원" 스타일 숫자)
# 느낌을 살리려고 씀. 다만 한글 음절을 2,581자(전체 11,172자의 23%)만 담고 있어서
# 종목명·테마명처럼 동적으로 들어오는 텍스트에 쓰면 못 그리는 글자가 네모(tofu)로
# 깨질 위험이 있음 — 그래서 그릴 문자열마다 커버리지를 확인해 안 되면 Noto Sans
# black 굵기로 자동 대체한다(예전에 이모지 깨짐 겪은 뒤로 정착한 안전 패턴과 동일).
FONT_DISPLAY = os.path.join(_FONTS_DIR, "BlackHanSans-Regular.ttf")
_DISPLAY_CMAP = set(TTFont(FONT_DISPLAY).getBestCmap().keys())
_DISPLAY_CACHE = {}


def _covers(text):
    return all(ord(ch) in _DISPLAY_CMAP or ch.isspace() for ch in text)


def _display_font(text, size):
    if not _covers(text):
        return font("black", size)
    if size not in _DISPLAY_CACHE:
        _DISPLAY_CACHE[size] = ImageFont.truetype(FONT_DISPLAY, size)
    return _DISPLAY_CACHE[size]


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


# ---------------- 카드별 렌더 ----------------

def render_cover(headline_lines, subtitle, date_str, page, total):
    img, d = _notepad_card()
    x0, y0, x1, y1 = CARD
    cx = (x0 + x1) // 2
    y = _masthead(img, d, x0 + 56, x1 - 56, y0 + 46, "장전 브리핑", f"{date_str} · 오늘의 한 장")

    y += 90
    n = len(headline_lines)
    for i, line in enumerate(headline_lines):
        color = ORANGE if i == n - 1 else INK
        _center_text(d, line, _display_font(line, 62), cx, y, color)
        y += 76
    y += 18
    d.line([(cx - 60, y), (cx + 60, y)], fill=RULE, width=3)
    y += 36
    if subtitle:
        for line in _wrap(d, subtitle, font("regular", 26), x1 - x0 - 200)[:2]:
            _center_text(d, line, font("regular", 26), cx, y, INK_SOFT)
            y += 38

    _footer(img, d, x0, x1, y1, date_str, page, total)
    return img


def render_market(data, date_str, page, total):
    img, d = _notepad_card()
    x0, y0, x1, y1 = CARD
    cx = (x0 + x1) // 2
    ix = data["us_indices"] or {}
    nasdaq_up = ix.get("nasdaq", {}).get("chg_pct", 0) >= 0
    headline = "미국은 웃었고, 환율은 올랐다" if nasdaq_up else "미국도 조심스럽고, 환율도 흔들렸다"

    y = _masthead(img, d, x0 + 56, x1 - 56, y0 + 46, "01 · 간밤 시장", f"{date_str}")
    _center_text(d, headline, _display_font(headline, 38), cx, y, INK)
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
        d.text((ex, y), f"어제({data['movers_date'][5:].replace('-', '.')}) 급등·급락 TOP3",
                font=font("bold", 25), fill=INK)
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


def render_earnings(data, date_str, page, total):
    img, d = _notepad_card()
    x0, y0, x1, y1 = CARD
    cx = (x0 + x1) // 2
    ex, ey = x0 + 56, x1 - 56
    y = _masthead(img, d, ex, ey, y0 + 46, "02 · 실적 발표", f"{date_str}")
    _center_text(d, "누가 웃고, 누가 울었나", _display_font("누가 웃고, 누가 울었나", 38), cx, y, INK)
    y += 70

    surprises = [e for e in data["earnings"] if e["tag"] == "surprise"][:3]
    shocks = [e for e in data["earnings"] if e["tag"] == "shock"][:2]

    if surprises:
        d.text((ex, y), "어닝 서프라이즈", font=font("bold", 23), fill=GOOD)
        y += 40
        for e in surprises:
            v = f"순이익 {_pct_text(e['ni_yoy'])}"
            _row(d, ex, ey, y, e["name"], v,
                 value_color=GOOD, dot_color=GOOD, value_font=_display_font(v, 28))
            y += 52
        y += 20

    if shocks:
        d.text((ex, y), "어닝 쇼크", font=font("bold", 23), fill=BAD)
        y += 40
        for e in shocks:
            v = f"순이익 {_pct_text(e['ni_yoy'])}"
            _row(d, ex, ey, y, e["name"], v,
                 value_color=BAD, dot_color=BAD, value_font=_display_font(v, 28))
            y += 40
            if e.get("rev_yoy") is not None:
                d.text((ex + 26, y), f"매출 {_pct_text(e['rev_yoy'])}", font=font("regular", 19), fill=DIM)
                y += 30
            y += 12

    _footer(img, d, x0, x1, y1, date_str, page, total)
    return img


_ANOMALY_HEADLINES = {
    "적자 전환": "흑자에서 적자로 전환",
    "비적정 감사의견": "감사의견, 적정 아님",
    "영업외 손익 의존": "영업이익 적자인데 순이익만 흑자",
    "부채비율 급증": "부채비율이 급격히 늘었다",
    "매출": "매출이 계속 줄고 있다",
}


def _anomaly_headline(anomalies):
    if not anomalies:
        return "오늘은 특별한 위험신호 없음"
    label = anomalies[0]["label"]
    for key, headline in _ANOMALY_HEADLINES.items():
        if key in label:
            return headline
    return "조심해서 봐야 할 재무 신호"


def render_anomaly(data, date_str, page, total):
    img, d = _notepad_card()
    x0, y0, x1, y1 = CARD
    cx = (x0 + x1) // 2
    ex, ey = x0 + 56, x1 - 56
    y = _masthead(img, d, ex, ey, y0 + 46, "03 · 위험 신호", f"{date_str}")
    ah = _anomaly_headline(data["anomalies"])
    _center_text(d, ah, _display_font(ah, 34), cx, y, INK)
    y += 76

    for a in data["anomalies"][:4]:
        cyc = y + 14
        d.ellipse([ex, cyc - 14, ex + 28, cyc + 14], outline=BAD, width=3)
        d.line([(ex + 14, cyc - 6), (ex + 14, cyc + 3)], fill=BAD, width=3)
        d.ellipse([ex + 12.5, cyc + 7, ex + 15.5, cyc + 10], fill=BAD)
        d.text((ex + 44, y), f"{a['name']} ({a['code']})", font=font("bold", 27), fill=INK)
        y += 56
        d.line([(ex, y - 8), (ey, y - 8)], fill=RULE, width=1)

    y += 20
    if data["anomalies"]:
        for line in _wrap(d, data["anomalies"][0]["text"], font("regular", 19), ey - ex):
            d.text((ex, y), line, font=font("regular", 19), fill=DIM)
            y += 28

    _footer(img, d, x0, x1, y1, date_str, page, total)
    return img


def render_theme_cta(data, date_str, page, total, section_no):
    img, d = _notepad_card()
    x0, y0, x1, y1 = CARD
    cx = (x0 + x1) // 2
    ex, ey = x0 + 56, x1 - 56
    themes = data["themes"]
    top = themes[0] if themes else None
    if top:
        sign = "+" if top["ret_1m"] >= 0 else ""
        headline = f"{top['mid']} 한 달 새 {sign}{top['ret_1m']:.1f}%"
    else:
        headline = "요즘 주도테마 한눈에 보기"

    y = _masthead(img, d, ex, ey, y0 + 46, f"{section_no:02d} · 주도테마", f"{date_str}")
    _center_text(d, headline, _display_font(headline, 34), cx, y, INK)
    y += 70

    for m in themes[:3]:
        tv = _pct_text(m["ret_1m"])
        _row(d, ex, ey, y, m["mid"], tv, value_color=_sign_color(m["ret_1m"]),
             label_font=font("regular", 27), value_font=_display_font(tv, 28))
        y += 46
        d.line([(ex, y - 10), (ey, y - 10)], fill=RULE, width=1)

    cta_y = y1 - 226
    d.rounded_rectangle([ex, cta_y, ey, cta_y + 130], radius=20, outline=ORANGE, width=3)
    _checkbox(d, ex + 26, cta_y + 24, size=26)
    d.text((ex + 66, cta_y + 20), "전 종목 스크리닝, 무료로", font=font("bold", 27), fill=INK)
    d.text((ex + 66, cta_y + 58), "재무제표 · 회계감사의견까지 한번에", font=font("regular", 19), fill=DIM)
    d.text((ex + 26, cta_y + 90), "getmoneycheckup.com", font=font("bold", 25), fill=ORANGE)

    _footer(img, d, x0, x1, y1, date_str, page, total)
    return img


def generate_cards(data, name_of, headline_lines, subtitle, date_str, out_dir="cards_out"):
    """data: app.py::_blog_draft_data() 결과. 섹션이 없는 날은 그 카드를 건너뛰어
    장수가 유동적으로 줄어든다(예: 실적발표 없는 날 실적 카드 생략)."""
    data = dict(data)
    data["_name_of"] = name_of
    os.makedirs(out_dir, exist_ok=True)

    sections = []
    if data["us_indices"] or data["gainers"] or data["losers"]:
        sections.append("market")
    if data["earnings"]:
        sections.append("earnings")
    if data["anomalies"]:
        sections.append("anomaly")
    # CTA(테마+CTA 카드)는 항상 마지막에 정확히 1장 — 테마 데이터가 없는 날도
    # CTA 자체는 있어야 하므로 섹션 유무와 무관하게 항상 추가한다.
    sections.append("theme_cta")

    total = 1 + len(sections)  # 총 장수를 렌더링 전에 먼저 확정(페이지 번호 불일치 방지)
    paths = []

    cover = render_cover(headline_lines, subtitle, date_str, 1, total)
    p = os.path.join(out_dir, "01.png")
    cover.save(p)
    paths.append(p)

    section_no = 1
    for i, kind in enumerate(sections, start=2):
        if kind == "market":
            img = render_market(data, date_str, i, total)
        elif kind == "earnings":
            img = render_earnings(data, date_str, i, total)
        elif kind == "anomaly":
            img = render_anomaly(data, date_str, i, total)
        elif kind == "theme_cta":
            img = render_theme_cta(data, date_str, i, total, section_no)
        p = os.path.join(out_dir, f"{i:02d}.png")
        img.save(p)
        paths.append(p)
        section_no += 1

    return paths
