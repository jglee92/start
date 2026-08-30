# -*- coding: utf-8 -*-
"""교육 가이드(blog_articles/*.txt)에 넣을 '개념 삽화'를 AI로 생성한다.

- 각 글의 제목·소제목(■)에서 주제를 뽑아, 글자 없는 교육용 일러스트를 1~2장 생성.
- static/guide_img/<hash>_N.png 로 저장하고 data/guide_images.json 매니페스트에
  {slug: {"imgs":[...], "hash":...}} 기록. content.py::render_guide가 이 매니페스트를
  읽어 본문 소제목(<h2>) 사이에 삽화를 끼워 넣는다(없으면 그냥 글만 — 안전 폴백).
- 내용 해시가 같으면 재생성 안 함(과금 0). 새 글이 생기면 그것만 생성.
- 카드와 달리 사진풍이 아니라 '깔끔한 플랫 일러스트'(개념 설명용). 이미지 안 글자 금지.

필요: IMAGE_API_KEY(imagegen_config). 없으면 아무것도 안 만들고 종료(글은 그대로).
사용: python generate_guide_images.py
"""
from __future__ import annotations
import os
import sys
import json
import base64
import hashlib
from io import BytesIO

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import requests
from PIL import Image
import app as A
import imagegen_config as IMG

BASE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE, "static", "guide_img")
MANIFEST = os.path.join(BASE, "data", "guide_images.json")


def _headings(body):
    return [ln.strip().lstrip("■").strip()
            for ln in body.split("\n") if ln.strip().startswith("■")]


def _prompt(topic):
    return (f"Clean minimal editorial illustration for a Korean personal-investing "
            f"education article, concept: '{topic}'. Flat vector style, soft muted "
            f"professional colors, friendly and clear (use simple charts, documents, "
            f"coins, magnifier, balance scale as fitting). Square composition. "
            f"Absolutely NO text, NO letters, NO numbers, NO logos, NO watermark.")


def _gen_one(prompt):
    """이미지 1장(PIL) 또는 None."""
    if not IMG.enabled() or IMG.IMAGE_PROVIDER != "openai":
        return None
    try:
        r = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {IMG.IMAGE_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": IMG.IMAGE_MODEL, "prompt": prompt, "size": "1024x1024"},
            timeout=180)
        if r.status_code != 200:
            print(f"::warning::이미지 API {r.status_code}: {r.text[:200]}")
            return None
        b64 = (r.json().get("data") or [{}])[0].get("b64_json")
        return Image.open(BytesIO(base64.b64decode(b64))).convert("RGB") if b64 else None
    except Exception as e:
        print(f"::warning::생성 실패: {e}")
        return None


def main():
    if not IMG.enabled():
        print("::warning::IMAGE_API_KEY 미설정 — 삽화 생성 건너뜀(글은 그대로 노출).")
        return
    os.makedirs(IMG_DIR, exist_ok=True)
    manifest = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            manifest = json.load(f)

    files = A._guide_files()
    print(f"가이드 {len(files)}편 점검")
    made = skipped = 0
    for slug, folder, path in files:
        title, category, body = A._parse_guide(path)
        heads = _headings(body)
        topics = [title] + heads[1:3]          # 제목 + 소제목 몇 개
        n = 2 if len(heads) >= 3 else 1
        topics = topics[:n]
        hkey = hashlib.sha1(("|".join([title] + heads)).encode("utf-8")).hexdigest()[:12]
        if manifest.get(slug, {}).get("hash") == hkey:
            skipped += 1
            continue
        h = hashlib.sha1(slug.encode("utf-8")).hexdigest()[:12]
        imgs = []
        for i, topic in enumerate(topics):
            img = _gen_one(_prompt(topic))
            if img:
                rel = f"guide_img/{h}_{i}.png"
                img.save(os.path.join(BASE, "static", rel))
                imgs.append(rel)
        if imgs:
            manifest[slug] = {"imgs": imgs, "hash": hkey}
            made += 1
            print(f"  [{slug[:24]}] 삽화 {len(imgs)}장")

    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"완료: 생성 {made} · 스킵(변동없음) {skipped} · 매니페스트 {len(manifest)}편")


if __name__ == "__main__":
    main()
