# -*- coding: utf-8 -*-
"""
데이터 provider 인터페이스.

지금은 fdr(무료 EOD)만 구현. 나중에 키움 계좌/32bit/로그인 준비되면
동일 인터페이스로 KiwoomProvider 를 끼워 실시간 전환한다.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class MarketSnapshot:
    """특정 거래일의 전 종목 스냅샷."""
    date: str                 # 'YYYY-MM-DD' (데이터 기준일)
    df: pd.DataFrame          # 표준 컬럼: code,name,market,open,high,low,close,
                              #           volume,amount,marcap,change_ratio


class DataProvider:
    name = "base"

    def get_market_snapshot(self) -> MarketSnapshot:
        """전 종목의 최신 거래일 스냅샷을 표준 스키마로 반환."""
        raise NotImplementedError

    def get_history(self, code: str, days: int) -> Optional[pd.DataFrame]:
        """종목 일봉 히스토리. 인덱스=date, 컬럼=open,high,low,close,volume."""
        raise NotImplementedError
