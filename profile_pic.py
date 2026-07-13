# -*- coding: utf-8 -*-
"""인스타 프로필 사진 생성 — static/icon-512.png(실제 머니체크업 브랜드 아이콘: 건강검진
실루엣+심전도 라인+체크 배지)를 그대로 가져다 카드뉴스와 같은 네이비 배경에 얹는다.
(이전 버전은 이 아이콘을 확인 안 하고 체크마크를 새로 그렸었음 — 실제 마크와 달라서
사용자가 지적, 이번에 실제 아이콘으로 교체.)
인스타는 프로필 사진을 원형으로 잘라서 보여주므로 안전 여백을 넉넉히 둔다."""
from __future__ import annotations
import os

from PIL import Image, ImageDraw, ImageFilter

from card_render import BG_TOP, BG_BOTTOM, ACCENT

SIZE = 1024
ICON_PATH = os.path.join(os.path.dirname(__file__), "static", "icon-512.png")


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

    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([SIZE * 0.15, SIZE * 0.1, SIZE * 0.95, SIZE * 0.9], fill=(*ACCENT, 30))
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

    icon = Image.open(ICON_PATH).convert("RGBA")
    icon = icon.crop(icon.getbbox())  # 여백 없는 실제 그림 영역만
    # 원형 크롭 안전영역(캔버스의 약 62%) 안에 들어오도록 큰 쪽 기준으로 스케일
    target = int(SIZE * 0.62)
    scale = target / max(icon.size)
    icon = icon.resize((int(icon.width * scale), int(icon.height * scale)), Image.LANCZOS)

    x = (SIZE - icon.width) // 2
    y = (SIZE - icon.height) // 2
    img = img.convert("RGBA")
    img.alpha_composite(icon, (x, y))
    img = img.convert("RGB")

    img.save(path)
    return path


if __name__ == "__main__":
    p = make_profile_pic("profile_pic.png")
    print(f"저장됨: {p}")
