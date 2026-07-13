# -*- coding: utf-8 -*-
"""인스타 프로필 사진 생성 — 카드뉴스 브랜드마크(체크+상승선 혼합 아이콘)를 단독으로
크게 키운 버전. 인스타는 프로필 사진을 원형으로 잘라서 보여주므로, 안전 여백을 넉넉히
두고 중앙에 배치 — 작게 보일 때도(댓글 목록 등 32px 크기) 알아볼 수 있게 굵고 단순하게."""
from __future__ import annotations
from PIL import Image, ImageDraw, ImageFilter

from card_render import BG_TOP, BG_BOTTOM, ACCENT, TXT

SIZE = 1024


def make_profile_pic(path="profile_pic.png"):
    img = Image.new("RGB", (SIZE, SIZE), BG_TOP)
    px = img.load()
    for y in range(SIZE):
        t = y / SIZE
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        for x in range(SIZE):
            px[x, y] = (r, g, b)

    # 은은한 중앙 글로우(원형 크롭 기준 안전영역 안에서만)
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([SIZE * 0.15, SIZE * 0.1, SIZE * 0.95, SIZE * 0.9], fill=(*ACCENT, 35))
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

    d = ImageDraw.Draw(img)
    cx, cy, r = SIZE / 2, SIZE / 2, SIZE * 0.24
    # 체크+상승선 마크(카드뉴스 브랜드마크와 동일 형태, 원형 크롭 안전영역 안에 크게)
    pts = [(cx - r, cy + r * 0.25), (cx - r * 0.15, cy + r * 0.95), (cx + r, cy - r)]
    d.line(pts, fill=ACCENT, width=int(SIZE * 0.052), joint="curve")
    for p in (pts[0], pts[-1]):
        rr = SIZE * 0.026
        d.ellipse([p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr], fill=ACCENT)  # 끝단 둥글림 보정

    img.save(path)
    return path


if __name__ == "__main__":
    p = make_profile_pic("profile_pic.png")
    print(f"저장됨: {p}")
