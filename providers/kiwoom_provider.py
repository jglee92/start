# -*- coding: utf-8 -*-
"""
키움 provider (자리표시자 / STUB).

실전(실시간) 단계에서 채운다. 준비물:
  1) 키움증권 계좌 + Open API 사용 신청
  2) [옵션 A] 구 OpenAPI+ : 32bit Windows Python + PyQt5 + KOA OCX + 로그인 팝업(대화형)
     [옵션 B] 신 REST API : 64bit 가능, appkey/appsecret 발급 후 토큰 인증(권장)
  3) 동일한 MarketSnapshot / get_history 스키마로 반환하도록 구현

지금은 fdr provider 로 1단계를 완성하고, 여기 구현은 실전 전환 때 붙인다.
"""
from __future__ import annotations
from typing import Optional
import pandas as pd

from .base import DataProvider, MarketSnapshot


class KiwoomProvider(DataProvider):
    name = "kiwoom"

    def get_market_snapshot(self) -> MarketSnapshot:
        raise NotImplementedError(
            "키움 provider 미구현. 실전 단계에서 계좌/키/환경 준비 후 구현. "
            "지금은 config.DATA_PROVIDER='fdr' 사용."
        )

    def get_history(self, code: str, days: int) -> Optional[pd.DataFrame]:
        raise NotImplementedError("키움 provider 미구현.")
