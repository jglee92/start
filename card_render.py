# -*- coding: utf-8 -*-
"""인스타 카드뉴스(캐러셀) 이미지 생성기. app.py::_blog_draft_data()의 구조화 데이터를
그대로 받아 1080x1080 PNG 여러 장을 만든다 — 완성된 텍스트를 다시 파싱하지 않음.

2026 인스타 카드뉴스 트렌드(부드러운 프리미엄 그라데이션·글래스모피즘·과감한 타이포
대비·스와이프할 때 이어지는 배경) 참고해서 리뉴얼함(이전 버전은 밋밋한 단색 박스라
"허접해 보인다"는 피드백을 받음).

브랜드 팔레트는 static/index.html의 실제 CSS 변수(--accent/--good/--bad)를 그대로
가져와 웹사이트와 동일한 톤을 유지하고, CTA 전용으로 주황색 하나만 새로 추가했다
(경고/위험엔 이미 있는 빨강을 쓰고, 주황은 오직 CTA·브랜드 강조에만 써서 의미가
섞이지 않게 함). 이모지는 폰트에 따라 네모(□)로 깨지는 걸 이미 겪어서(Noto CJK류에
컬러이모지 없음) 전부 벡터 도형(삼각형/원/느낌표)으로 대체."""
from __future__ import annotations
import os

from PIL import Image, ImageDraw, ImageFont, ImageFilter

W = H = 1080
PAD = 72

# Malgun Gothic(윈도우 시스템 폰트)은 라이선스상 리포에 번들해서 GitHub Actions(리눅스)
# 서버에 배포할 수 없음 — 대신 오픈라이선스(SIL OFL)인 Noto Sans KR 가변폰트를
# assets/fonts/에 직접 번들해서 로컬(윈도우)·CI(리눅스) 어디서든 동일하게 렌더링되게 함.
FONT_PATH = os.path.join(os.path.dirname(__file__), "assets", "fonts", "NotoSansKR-VF.ttf")
_WEIGHTS = {"light": 300, "regular": 400, "bold": 700}
_FONT_CACHE = {}


def font(weight, size):
    key = (weight, size)
    if key not in _FONT_CACHE:
        f = ImageFont.truetype(FONT_PATH, size)
        f.set_variation_by_axes([_WEIGHTS[weight]])
        _FONT_CACHE[key] = f
    return _FONT_CACHE[key]


# --- 브랜드 팔레트 (static/index.html --accent/--good/--bad 그대로) ---
BG_TOP = (8, 10, 18)
BG_BOTTOM = (22, 22, 46)     # 살짝 보라 섞은 남색 — 밋밋한 순수 네이비 탈피
ACCENT = (74, 143, 212)      # --accent
ACCENT2 = (124, 109, 224)    # 보조 그라데이션용(블루→바이올렛), 강조엔 안 씀
GOOD = (55, 194, 129)        # --good
BAD = (242, 85, 90)          # --bad
ORANGE = (255, 141, 61)      # CTA/브랜드 강조 전용(경고엔 안 씀)
TXT = (241, 244, 248)        # --txt
DIM = (170, 182, 194)        # --dim
LINE = (255, 255, 255)       # 글래스 패널 보더용(낮은 알파와 함께 사용)


def _bg(page=1, total=5):
    """부드러운 프리미엄 그라데이션(남색→살짝 보랏빛) + 두 개의 은은한 글로우.
    글로우 위치를 page/total 비율로 슬라이드시켜서, 캐러셀을 넘길 때 배경이 하나로
    이어지는 듯한 느낌을 준다(2026 트렌드: seamless panoramic carousel)."""
    img = Image.new("RGB", (W, H), BG_TOP)
    px = img.load()
    for y in range(H):
        t = y / H
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        for x in range(0, W, 4):  # 4px 스텝으로 근사 — 그라데이션엔 육안차이 없고 훨씬 빠름
            for xx in range(x, min(x + 4, W)):
                px[xx, y] = (r, g, b)
    img = img.convert("RGBA")

    prog = (page - 1) / max(total - 1, 1)  # 0(표지)~1(마지막 카드)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gx = int(W * (1.05 - prog * 0.5))  # 오른쪽에서 서서히 왼쪽으로
    gd.ellipse([gx - 340, -300, gx + 340, 380], fill=(*ACCENT, 55))
    gd.ellipse([-260, H - 420 + prog * 140, 340, H + 260], fill=(*ACCENT2, 30))
    glow = glow.filter(ImageFilter.GaussianBlur(130))
    img = Image.alpha_composite(img, glow)

    # 은은한 라인차트 워터마크(우상단→좌하단 대각, 낮은 불투명도)
    wm = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wm)
    pts = [(120, 760), (300, 700), (430, 780), (600, 560), (760, 620),
           (900, 420), (1040, 480)]
    wd.line(pts, fill=(*TXT, 12), width=6, joint="curve")
    img = Image.alpha_composite(img, wm)
    return img


def _glass_panel(img, x, y, w, h, radius=22, tint=None, border=None):
    """글래스모피즘(반투명 유리) 패널 — 배경을 크롭해서 블러 처리한 뒤 옅은 틴트를
    얹고 은은한 테두리를 그린다. 예전엔 flat한 단색 박스라 밋밋했는데, 이걸로
    바꾸면 배경이 은은히 비치는 '유리판' 느낌이 나서 훨씬 고급스러워 보인다."""
    x0, y0, x1, y1 = int(x), int(y), int(x + w), int(y + h)
    pad = 40  # 블러 경계 아티팩트 방지용 여유
    crop_box = (max(x0 - pad, 0), max(y0 - pad, 0), min(x1 + pad, W), min(y1 + pad, H))
    region = img.crop(crop_box).filter(ImageFilter.GaussianBlur(18))

    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=255)

    blurred_full = img.copy()
    blurred_full.paste(region, crop_box)
    img.paste(blurred_full, (0, 0), mask)

    tint_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    td = ImageDraw.Draw(tint_layer)
    tint_color = tint or (255, 255, 255, 26)
    td.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=tint_color)
    img.alpha_composite(tint_layer)

    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius, outline=border or (*LINE, 46), width=2)


def _wrap(draw, text, fnt, max_w):
    words = list(text)  # 한글은 어절 단위보다 글자 단위 랩이 실무적으로 더 안전(공백 적음)
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


ICON_PATH = os.path.join(os.path.dirname(__file__), "static", "icon-512.png")
_ICON_CACHE = {}


def _load_icon(size):
    """실제 머니체크업 브랜드 아이콘(static/icon-512.png) — 예전엔 이걸 확인 안 하고
    체크마크를 새로 그려서 실제 마크와 다르다는 지적을 받았음. 이제 원본을 그대로 축소."""
    if size not in _ICON_CACHE:
        icon = Image.open(ICON_PATH).convert("RGBA")
        icon = icon.crop(icon.getbbox())
        scale = size / max(icon.size)
        icon = icon.resize((max(1, int(icon.width * scale)), max(1, int(icon.height * scale))),
                            Image.LANCZOS)
        _ICON_CACHE[size] = icon
    return _ICON_CACHE[size]


def _brand_mark(img, x, y, size=28):
    icon = _load_icon(size)
    img.paste(icon, (int(x), int(y)), icon)


def _footer(img, draw, date_str, page, total):
    y = H - PAD - 8
    _brand_mark(img, PAD, y - 24, size=30)
    draw.text((PAD + 36, y - 24), "머니체크업", font=font("bold", 20), fill=TXT)
    draw.text((PAD + 36, y + 2), date_str, font=font("regular", 16), fill=DIM)
    page_txt = f"{page:02d} / {total:02d}"
    tw = draw.textlength(page_txt, font=font("regular", 20))
    draw.text((W - PAD - tw, y - 10), page_txt, font=font("regular", 20), fill=DIM)


def _header(draw, eyebrow, headline_lines, subtitle=None, eyebrow_color=None, y=PAD):
    """타이포 대비를 이전보다 키움(헤드라인 58→66px) — 2026 트렌드가 강조하는
    '한눈에 위계가 보이는 과감한 크기 대비'를 반영."""
    eyebrow_color = eyebrow_color or ACCENT
    draw.text((PAD, y), eyebrow.upper(), font=font("bold", 23), fill=eyebrow_color)
    y += 48
    for line in headline_lines:
        draw.text((PAD, y), line, font=font("bold", 66), fill=TXT)
        y += 78
    if subtitle:
        y += 8
        draw.text((PAD, y), subtitle, font=font("regular", 26), fill=DIM)
        y += 40
    return y


def _hline(draw, y, x0=PAD, x1=W - PAD, color=None):
    draw.line([(x0, y), (x1, y)], fill=color or (255, 255, 255, 30), width=1)


def _pct_text(v):
    return f"{v:+.1f}%"


def _sign_color(v):
    return GOOD if v is not None and v >= 0 else BAD


# ---------------- 카드별 렌더 ----------------

def render_cover(headline_lines, subtitle, date_str, page, total):
    img = _bg(page, total)
    d = ImageDraw.Draw(img)
    eyebrow = f"{date_str} · 장전 브리핑"
    y = _header(d, eyebrow, headline_lines, subtitle, y=320)
    d.rounded_rectangle([PAD, y + 4, PAD + 70, y + 9], radius=3, fill=ORANGE)
    _footer(img, d, date_str, page, total)
    return img.convert("RGB")


def render_market(data, date_str, page, total):
    img = _bg(page, total)
    d = ImageDraw.Draw(img)
    ix = data["us_indices"] or {}
    nasdaq_up = ix.get("nasdaq", {}).get("chg_pct", 0) >= 0
    headline = ["미국은 웃었고", "환율은 올랐다"] if nasdaq_up else ["미국도 조심스럽고", "환율도 흔들렸다"]
    y = _header(d, "01 · 간밤 시장 흐름", headline, y=PAD)

    y += 16
    cols = [("nasdaq", "나스닥"), ("sp500", "S&P 500"), ("usdkrw", "원달러")]
    col_w = (W - 2 * PAD) / 3
    stat_h = 118
    _glass_panel(img, PAD, y, W - 2 * PAD, stat_h)
    d = ImageDraw.Draw(img)
    for i, (key, label) in enumerate(cols):
        v = ix.get(key)
        x = PAD + 28 + i * col_w
        d.text((x, y + 20), label, font=font("regular", 21), fill=DIM)
        if v and key != "usdkrw" and v.get("chg_pct") is not None:
            txt, color = _pct_text(v["chg_pct"]), _sign_color(v["chg_pct"])
        elif v and key == "usdkrw" and v.get("price"):
            txt, color = f"{v['price']:,.1f}원", GOOD
        else:
            txt, color = "-", DIM
        d.text((x, y + 52), txt, font=font("bold", 33), fill=color)
    y += stat_h + 34

    if data["movers_date"]:
        d.text((PAD, y), f"어제({data['movers_date'][5:].replace('-', '.')}) 급등·급락 TOP3",
                font=font("bold", 26), fill=TXT)
        y += 50
        half = (W - 2 * PAD) / 2
        gy = y
        d.polygon([(PAD, gy + 14), (PAD + 22, gy + 14), (PAD + 11, gy - 4)], fill=GOOD)
        d.text((PAD + 34, gy - 8), "급등", font=font("bold", 22), fill=GOOD)
        gx2 = PAD + half
        d.polygon([(gx2, gy + 14), (gx2 + 22, gy + 14), (gx2 + 11, gy + 32)], fill=BAD)
        d.text((gx2 + 34, gy - 8), "급락", font=font("bold", 22), fill=BAD)
        y += 58
        from itertools import zip_longest
        for gainer, loser in zip_longest(data["gainers"], data["losers"]):
            if gainer:
                d.text((PAD, y), data["_name_of"](gainer[0]), font=font("regular", 26), fill=TXT)
                d.text((PAD, y + 34), _pct_text(gainer[1]), font=font("bold", 30), fill=GOOD)
            if loser:
                d.text((PAD + half, y), data["_name_of"](loser[0]), font=font("regular", 26), fill=TXT)
                d.text((PAD + half, y + 34), _pct_text(loser[1]), font=font("bold", 30), fill=BAD)
            y += 92

    _footer(img, d, date_str, page, total)
    return img.convert("RGB")


def render_earnings(data, date_str, page, total):
    img = _bg(page, total)
    d = ImageDraw.Draw(img)
    y = _header(d, "02 · 실적 발표 체크", ["누가 웃고", "누가 울었나"], y=PAD)
    y += 20

    surprises = [e for e in data["earnings"] if e["tag"] == "surprise"][:3]
    shocks = [e for e in data["earnings"] if e["tag"] == "shock"][:2]
    box_w = W - 2 * PAD
    if bool(surprises) != bool(shocks):
        y += 70  # 둘 중 하나만 있는 날엔 위로 쏠려 보이니 약간 아래로 내려 균형

    if surprises:
        row_h = 64
        box_h = 56 + row_h * len(surprises)
        _glass_panel(img, PAD, y, box_w, box_h, tint=(*GOOD, 22), border=(*GOOD, 90))
        d = ImageDraw.Draw(img)
        bx, by = PAD + 28, y + 24
        d.ellipse([bx, by + 4, bx + 14, by + 18], fill=GOOD)
        d.text((bx + 26, by - 4), "어닝 서프라이즈", font=font("bold", 24), fill=GOOD)
        by += 48
        for e in surprises:
            d.text((bx, by), e["name"], font=font("regular", 26), fill=TXT)
            txt = f"순이익 {_pct_text(e['ni_yoy'])}"
            tw = d.textlength(txt, font=font("bold", 26))
            d.text((PAD + box_w - 28 - tw, by), txt, font=font("bold", 26), fill=GOOD)
            by += row_h
        y += box_h + 26

    if shocks:
        row_h = 64
        # 매출 서브텍스트 한 줄이 마지막 엔트리 아래로 삐져나가는 문제가 있었음(+20으론
        # 부족해서 박스 테두리에 살짝 겹침, 개수 무관하게 고정적으로 발생) — +40으로 여유.
        box_h = 56 + row_h * len(shocks) + 40
        _glass_panel(img, PAD, y, box_w, box_h, tint=(*BAD, 22), border=(*BAD, 90))
        d = ImageDraw.Draw(img)
        bx, by = PAD + 28, y + 24
        d.ellipse([bx, by + 4, bx + 14, by + 18], fill=BAD)
        d.text((bx + 26, by - 4), "어닝 쇼크", font=font("bold", 24), fill=BAD)
        by += 48
        for e in shocks:
            d.text((bx, by), e["name"], font=font("regular", 26), fill=TXT)
            txt = f"순이익 {_pct_text(e['ni_yoy'])}"
            tw = d.textlength(txt, font=font("bold", 26))
            d.text((PAD + box_w - 28 - tw, by), txt, font=font("bold", 26), fill=BAD)
            by += row_h
            if e.get("rev_yoy") is not None:
                d.text((bx, by - 14), f"매출 {_pct_text(e['rev_yoy'])}", font=font("regular", 20), fill=DIM)
        y += box_h + 26

    _footer(img, d, date_str, page, total)
    return img.convert("RGB")


_ANOMALY_HEADLINES = {
    "적자 전환": ["흑자에서", "적자로 전환"],
    "비적정 감사의견": ["감사의견", "적정 아님"],
    "영업외 손익 의존": ["영업이익 적자,", "순이익만 흑자"],
    "부채비율 급증": ["부채비율", "급격히 늘었다"],
    "매출": ["매출이", "계속 줄고 있다"],  # '매출 2년/2분기 연속 감소' 공통 매칭
}


def _anomaly_headline(anomalies):
    if not anomalies:
        return ["오늘은 특별한", "위험신호 없음"]
    label = anomalies[0]["label"]
    for key, headline in _ANOMALY_HEADLINES.items():
        if key in label:
            return headline
    return ["조심해서 봐야 할", "재무 신호"]


def render_anomaly(data, date_str, page, total):
    """경고 카드 — CTA(주황) 색과 섞이지 않게 위험신호는 항상 빨강 계열로 통일.
    이제 이상신호가 항상 '적자전환'만 나오는 게 아니라(로테이션으로 다양해짐),
    헤드라인도 실제 1번 항목 라벨에 맞춰 동적으로 바뀐다."""
    img = _bg(page, total)
    d = ImageDraw.Draw(img)
    y = _header(d, "03 · 조심해서 봐야 할 신호", _anomaly_headline(data["anomalies"]),
                eyebrow_color=BAD, y=PAD)
    y += 20
    box_h, gap = 88, 18
    for a in data["anomalies"][:3]:
        _glass_panel(img, PAD, y, W - 2 * PAD, box_h, tint=(*BAD, 20), border=(*BAD, 85))
        d = ImageDraw.Draw(img)
        cx, cy = PAD + 44, y + box_h / 2
        d.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], outline=BAD, width=3)
        d.line([(cx, cy - 7), (cx, cy + 3)], fill=BAD, width=3)
        d.ellipse([cx - 1.5, cy + 8, cx + 1.5, cy + 11], fill=BAD)
        d.text((PAD + 78, y + box_h / 2 - 16), f"{a['name']} ({a['code']})",
                font=font("bold", 28), fill=TXT)
        y += box_h + gap
    y += 10
    if data["anomalies"]:
        d.text((PAD, y), data["anomalies"][0]["text"], font=font("regular", 20), fill=DIM)

    _footer(img, d, date_str, page, total)
    return img.convert("RGB")


def render_theme_cta(data, date_str, page, total, section_no):
    img = _bg(page, total)
    d = ImageDraw.Draw(img)
    themes = data["themes"]
    top = themes[0] if themes else None
    if top:
        sign = "+" if top["ret_1m"] >= 0 else ""
        headline = [f"{top['mid']}", f"한 달 새 {sign}{top['ret_1m']:.1f}%"]
    else:
        headline = ["요즘 주도테마", "한눈에 보기"]
    y = _header(d, f"{section_no:02d} · 요즘 주도테마", headline, y=PAD)
    y += 20

    for m in themes[:3]:
        d.text((PAD, y), m["mid"], font=font("regular", 28), fill=TXT)
        txt = _pct_text(m["ret_1m"])
        tw = d.textlength(txt, font=font("bold", 30))
        d.text((W - PAD - tw, y - 2), txt, font=font("bold", 30), fill=_sign_color(m["ret_1m"]))
        y += 44
        _hline(d, y)
        y += 34

    cta_y = H - PAD - 210
    cta_h = 150
    _glass_panel(img, PAD, cta_y, W - 2 * PAD, cta_h, tint=(*ORANGE, 24), border=(*ORANGE, 110))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([PAD, cta_y, PAD + 8, cta_y + cta_h], radius=4, fill=ORANGE)
    tx = PAD + 34
    d.text((tx, cta_y + 22), "전 종목 스크리닝, 무료로", font=font("bold", 28), fill=TXT)
    d.text((tx, cta_y + 62), "재무제표 · 회계감사의견까지 한번에", font=font("regular", 20), fill=DIM)
    d.ellipse([tx, cta_y + 104, tx + 12, cta_y + 116], fill=ACCENT)
    d.text((tx + 24, cta_y + 100), "getmoneycheckup.com", font=font("bold", 26), fill=ACCENT)

    _footer(img, d, date_str, page, total)
    return img.convert("RGB")


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
