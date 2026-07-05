# -*- coding: utf-8 -*-
"""FinanceDataReader 기반 provider (무료 EOD, 계좌/키 불필요)."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import FinanceDataReader as fdr

from .base import DataProvider, MarketSnapshot


class FdrProvider(DataProvider):
    name = "fdr"

    def get_market_snapshot(self) -> MarketSnapshot:
        raw = fdr.StockListing("KRX")
        # FDR 컬럼 -> 표준 스키마
        df = pd.DataFrame({
            "code": raw["Code"].astype(str).str.zfill(6),
            "name": raw["Name"],
            "market": raw["Market"],
            "open": raw["Open"],
            "high": raw["High"],
            "low": raw["Low"],
            "close": raw["Close"],
            "volume": raw["Volume"],
            "amount": raw["Amount"],        # 거래대금(원)
            "marcap": raw["Marcap"],        # 시가총액(원)
            "change_ratio": raw["ChagesRatio"],  # 등락률(%) — FDR 철자 그대로
        })
        # 숫자화 + 결측/0 정리
        num_cols = ["open", "high", "low", "close", "volume",
                    "amount", "marcap", "change_ratio"]
        for c in num_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["close", "amount", "marcap"])
        df = df[df["close"] > 0]

        # 스냅샷 기준일: 마지막 거래일을 최근 종목 히스토리로 추정
        snap_date = self._infer_snapshot_date(df)
        return MarketSnapshot(date=snap_date, df=df.reset_index(drop=True))

    def get_history(self, code: str, days: int) -> Optional[pd.DataFrame]:
        end = datetime.now()
        start = end - timedelta(days=days)
        try:
            h = fdr.DataReader(code, start.strftime("%Y-%m-%d"),
                               end.strftime("%Y-%m-%d"))
        except Exception:
            return None
        if h is None or len(h) == 0:
            return None
        h = h.rename(columns=str.lower)
        keep = [c for c in ["open", "high", "low", "close", "volume"] if c in h.columns]
        return h[keep]

    def _infer_snapshot_date(self, df: pd.DataFrame) -> str:
        """StockListing 은 기준일을 안 주므로, 대표 종목(삼성전자) 최근 봉 날짜로 추정."""
        try:
            h = self.get_history("005930", 10)
            if h is not None and len(h):
                return h.index[-1].strftime("%Y-%m-%d")
        except Exception:
            pass
        return datetime.now().strftime("%Y-%m-%d")
