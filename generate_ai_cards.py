# -*- coding: utf-8 -*-
"""반자동 AI 배경 카드 — 오늘 데이터로 '정직한' 헤드라인을 뽑고, AI로 생성한 배경
이미지(글자 없는 배경) 위에 그 텍스트를 합성해 후보 여러 장을 저장한다. 사용자가
그중 골라 인스타에 올린다(반자동 — 완전자동은 금융 브랜드에 어색한 이미지가 그대로
나갈 위험이 있어 배제).

- 톤: 사실 후킹만. 헤드라인은 card_templates.pick_cover_headline 재사용(예측·수익률
  단정 없음 = 우리 정직 브랜드 유지). 이미지 프롬프트에도 예측/문구를 넣지 않는다.
- 배경: imagegen_config로 이미지 생성 API 호출(배경만, 글자 없음). 키가 없으면
  폴백 그라디언트로라도 후보를 만들어 레이아웃 확인이 가능하게 함(파이프라인 안 죽음).
- 합성/폰트: card_render의 폰트를 재사용(브랜드 일관성) + 하단 스크림으로 흰 글자 가독성.

출력: content_out/<date>/ai_card_candidates/cand_1.png ..  (사용자가 골라서 사용)
사용: python generate_ai_cards.py
"""
from __future__ import annotations
import os
import sys
import base64
from io import BytesIO

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from PIL import Image, ImageDraw
import app as A
import caption_generator
import card_render as CR
import card_templates
import imagegen_config as IMG

W = H = CR.W   # 1080


# ── 배경 프롬프트(정직·글자 없음) ────────────────────────────────────────────
def _scene_for(data):
    """오늘 데이터의 지배적 신호에서 '분위기 장면'을 고른다. 특정 예측/문구가 아니라
    무드만 — 이미지엔 절대 글자를 넣지 않는다."""
    ix = (data.get("us_indices") or {})
    kospi = ix.get("kospi") or {}
    chg = kospi.get("chg_pct")
    if chg is not None and chg <= -1.0:
        return ("a moody dark city skyline of Seoul at dusk under heavy clouds, "
                "cold blue tones, sense of tension")
    if chg is not None and chg >= 1.0:
        return ("a bright modern Seoul financial district skyline at sunrise, "
                "warm optimistic light")
    themes = data.get("themes") or []
    if themes:
        return ("an abstract cinematic representation of industry and technology, "
                "sleek modern, soft studio lighting")
    return ("a calm modern financial workspace, soft natural light, minimal desk "
            "with subtle out-of-focus charts in the background")


# 섹션별 배경 '무드' 장면(글자·예측 없음). 각 카드 주제에 맞춘 분위기만.
_SECTION_SCENE = {
    "signals": "a dark wooden desk with a financial newspaper and a magnifying glass, "
               "investigative and cautious mood, dramatic side lighting",
    "theme": "an abstract cinematic montage of modern industry and technology, sleek "
             "surfaces, soft studio lighting, sense of momentum",
    "company": "a modern corporate headquarters glass building seen from below at blue "
               "hour, calm professional mood",
}


def _prompt(scene):
    # 글자·숫자·워터마크 금지를 강하게 명시(이미지 안 글자는 AI가 못 그려서 반드시 배제).
    return (f"Editorial cinematic photograph, {scene}. High detail, professional "
            f"finance-magazine cover aesthetic, vertical 1:1 composition with calm "
            f"empty space in the lower third for a text overlay. "
            f"Absolutely NO text, NO letters, NO numbers, NO logos, NO watermark.")


# ── 배경 생성 어댑터 ─────────────────────────────────────────────────────────
def _gen_backgrounds(prompt, n):
    """이미지 생성 API로 배경 n장(PIL). 키/공급자 없으면 None(폴백은 호출부에서)."""
    if not IMG.enabled():
        return None
    if IMG.IMAGE_PROVIDER == "openai":
        import requests
        out = []
        # 1장씩 n번 호출 — n>1 미지원 모델·부분 실패에도 견고(가능한 만큼 확보).
        for k in range(n):
            try:
                r = requests.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={"Authorization": f"Bearer {IMG.IMAGE_API_KEY}",
                             "Content-Type": "application/json"},
                    json={"model": IMG.IMAGE_MODEL, "prompt": prompt, "size": "1024x1024"},
                    timeout=180)
                if r.status_code != 200:
                    print(f"::warning::이미지 API {r.status_code}: {r.text[:200]}")
                    continue
                b64 = (r.json().get("data") or [{}])[0].get("b64_json")
                if b64:
                    out.append(Image.open(BytesIO(base64.b64decode(b64))).convert("RGB"))
            except Exception as e:
                print(f"::warning::이미지 생성 실패({k+1}/{n}): {e}")
        return out or None
    print(f"::warning::알 수 없는 IMAGE_PROVIDER={IMG.IMAGE_PROVIDER}")
    return None


def _fallback_bg(i):
    """키 없을 때 레이아웃 확인용 그라디언트 배경(어두운 남색→검정)."""
    top = [(18, 24, 38), (30, 18, 24), (16, 28, 26)][i % 3]
    img = Image.new("RGB", (W, H), top)
    px = img.load()
    for y in range(H):
        f = y / H
        px_row = tuple(int(c * (1 - 0.75 * f)) for c in top)
        for x in range(W):
            px[x, y] = px_row
    return img


def _fill_square(img):
    """어떤 비율이든 1080x1080으로 꽉 채우게 center-crop."""
    img = img.convert("RGB")
    s = min(img.size)
    l = (img.width - s) // 2
    t = (img.height - s) // 2
    return img.crop((l, t, l + s, t + s)).resize((W, H), Image.LANCZOS)


# ── 합성 ─────────────────────────────────────────────────────────────────────
def _apply_scrim(img):
    """하단 2/3에 아래로 갈수록 진해지는 검은 스크림 — 어떤 배경에도 흰 글자 가독성 확보."""
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for y in range(H):
        f = max(0.0, (y - H * 0.33) / (H * 0.67))
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(200 * f * f)))
    # 상단에도 살짝(브랜드 마크 가독성)
    for y in range(int(H * 0.16)):
        a = int(120 * (1 - y / (H * 0.16)))
        d.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def _compose(bg, headline_lines, subtitle, date_str):
    img = _apply_scrim(_fill_square(bg))
    d = ImageDraw.Draw(img)
    M = 70
    # 브랜드 마크(상단)
    d.text((M, 46), "머니체크업", font=CR.font("bold", 34), fill=(255, 255, 255))
    d.text((W - M, 52), date_str, font=CR.font("regular", 28), fill=(210, 210, 210),
           anchor="ra")
    # 헤드라인 — pick_cover_headline이 이미 2줄로 설계해 주므로 그 줄바꿈을 그대로 쓰고,
    # 폭에 맞을 때까지 폰트만 줄인다(재줄바꿈하면 '+294%' 같은 숫자가 중간에서 쪼개짐).
    lines = [ln for ln in (headline_lines if isinstance(headline_lines, (list, tuple))
                           else [headline_lines]) if ln]
    text = " ".join(lines)
    size = 88
    fnt = CR._display_font(text, size)
    while size > 44 and any(d.textlength(ln, font=fnt) > W - 2 * M for ln in lines):
        size -= 4
        fnt = CR._display_font(text, size)
    lh = int(size * 1.22)
    sub_fnt = CR.font("bold", 40)
    sub_lines = CR._wrap(d, subtitle or "", sub_fnt, W - 2 * M) if subtitle else []
    block_h = len(lines) * lh + (len(sub_lines) * 52 + 24 if sub_lines else 0)
    y = H - 90 - block_h
    for ln in lines:
        d.text((M, y), ln, font=fnt, fill=(255, 255, 255))
        y += lh
    if sub_lines:
        y += 24
        for ln in sub_lines:
            d.text((M, y), ln, font=sub_fnt, fill=(240, 224, 150))  # 포인트 컬러
            y += 52
    return img


def _safe(fn, data, seed):
    """card_templates의 _t_* 헤드라인 함수를 안전하게 호출 → (lines, subtitle) 또는 None."""
    try:
        lines, sub, _ = fn(data, seed)
        return (lines, sub) if lines else None
    except Exception:
        return None


def _specs(data, date_str):
    """섹션별 (라벨, 헤드라인, 부제, 배경장면) 목록. 데이터 있는 섹션만. 헤드라인은
    card_templates의 사실 기반 문구 재사용(예측·과장 없음 = 정직 톤 유지)."""
    CT = card_templates
    data["_trend"] = CT._detect_trend(data)
    seed = date_str
    out = []
    # 1) 표지 — 그날 임팩트 큰 사실 헤드라인(로테이션). 배경은 지수 방향 무드.
    hl, sub, _tid = CT.pick_cover_headline(data, A._name_of, date_str)
    out.append(("cover", hl, sub, _scene_for(data)))
    # 2) 급등주(시장)
    if data.get("gainers"):
        r = _safe(CT._t_gainer_pct, data, seed + "|g")
        if r:
            out.append(("gainers", r[0], r[1], _scene_for(data)))
    # 3) 시그널(실적/이상신호)
    if data.get("earnings"):
        r = _safe(CT._t_earnings_split, data, seed + "|e")
        if r:
            out.append(("signals", r[0], r[1], _SECTION_SCENE["signals"]))
    elif data.get("anomalies"):
        r = _safe(CT._t_anomaly_count, data, seed + "|a")
        if r:
            out.append(("signals", r[0], r[1], _SECTION_SCENE["signals"]))
    # 4) 테마
    if data.get("themes"):
        r = _safe(CT._t_theme_hot, data, seed + "|t")
        if r:
            out.append(("theme", r[0], r[1], _SECTION_SCENE["theme"]))
    # 5) 오늘의 기업 종합검진(featured) — 데이터 덱의 마지막 장과 동일 컨셉
    f = data.get("featured")
    if f and f.get("name"):
        score = f.get("score")
        hl = ["오늘의 기업 검진", str(f["name"])]
        sub = (f"건강점수 {score:.0f}점 · 가치+퀄리티로 살펴본 현주소"
               if score is not None else "가치+퀄리티 팩터로 살펴본 현주소")
        out.append(("company", hl, sub, _SECTION_SCENE["company"]))
    return out


def main():
    force = "--force" in sys.argv   # 휴장일에도 생성(테스트용)
    data = A._blog_draft_data()
    if data.get("is_holiday") and not force:
        print("휴장일 — AI 카드 생성 안 함(--force로 강제 가능).")
        return
    data["_name_of"] = A._name_of
    date_str = data["date"].strftime("%Y-%m-%d")
    specs = _specs(data, date_str)
    print(f"섹션 {len(specs)}장: {[s[0] for s in specs]}")

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "content_out", date_str, "ai_card_candidates")
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):   # 이전 실행 잔여물(옛 cand_*.png 등) 정리
        if f.endswith(".png"):
            os.remove(os.path.join(out_dir, f))
    made = 0
    for label, hl, sub, scene in specs:
        bg = _gen_backgrounds(_prompt(scene), 1)
        if bg:
            bg = bg[0]
        else:
            print(f"  [{label}] 이미지 API 미설정/실패 — 폴백 배경 사용.")
            bg = _fallback_bg(made)
        card = _compose(bg, hl, sub, date_str.replace("-", "."))
        p = os.path.join(out_dir, f"{label}.png")
        card.save(p)
        made += 1
        print(f"  저장: {p}  | {' '.join(hl) if isinstance(hl,(list,tuple)) else hl}")

    # 인스타 캡션 — 옛 daily_content의 cards/caption.txt를 대체(2026-09-02). 카드와 같은
    # 폴더(ai_card_candidates)에 넣어, 카드를 고른 뒤 캡션을 바로 복사해 쓸 수 있게 한다.
    # 표지 헤드라인/부제를 캡션 첫 줄로 재사용(카드 톤과 캡션 톤 일치).
    if specs:
        cover_hl, cover_sub = specs[0][1], specs[0][2]
        try:
            caption = caption_generator.build_caption(
                data, cover_hl, cover_sub, date_str)
            with open(os.path.join(out_dir, "caption.txt"), "w", encoding="utf-8") as cf:
                cf.write(caption)
            print("  저장: caption.txt")
        except Exception as e:
            print(f"::warning::캡션 생성 실패(카드는 정상): {e}")

    print(f"\n섹션 카드 {made}장 저장 완료 → 골라서 인스타에 사용하세요.")


if __name__ == "__main__":
    main()
