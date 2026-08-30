# -*- coding: utf-8 -*-
"""AI 카드 배경 이미지 생성 설정 — Claude(Anthropic)는 이미지를 못 만들므로 별도
이미지 생성 API가 필요하다. 키를 발급받아 환경변수/시크릿으로 넣으면 활성화되고,
없으면 generate_ai_cards.py가 폴백 그라디언트 배경으로만 후보를 만든다(파이프라인
안 죽음).

기본 공급자는 OpenAI 이미지 API(gpt-image-1) — 사진풍 배경 품질이 좋고 API가 단순.
다른 공급자를 쓰려면 generate_ai_cards.py::_gen_backgrounds()에 어댑터를 추가하면 됨.
"""
import os

# "openai" | None(비활성). 키가 있어야 실제로 생성됨.
IMAGE_PROVIDER = "openai"
# 환경변수에서 읽음(코드/깃에 키를 박지 않는다). GitHub Actions면 시크릿으로 주입.
IMAGE_API_KEY = os.getenv("IMAGE_API_KEY") or os.getenv("OPENAI_API_KEY")
IMAGE_MODEL = "gpt-image-1"
# 하루에 만들 후보 장수(사용자가 이 중 골라 게시). 비용 = 장수 × 모델 단가.
CANDIDATES_PER_DAY = 3


def enabled():
    return bool(IMAGE_PROVIDER and IMAGE_API_KEY)
