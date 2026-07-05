# -*- coding: utf-8 -*-
from .base import DataProvider, MarketSnapshot


def get_provider(name: str) -> DataProvider:
    if name == "fdr":
        from .fdr_provider import FdrProvider
        return FdrProvider()
    if name == "kiwoom":
        from .kiwoom_provider import KiwoomProvider
        return KiwoomProvider()
    raise ValueError(f"Unknown provider: {name!r}")
