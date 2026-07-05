# -*- coding: utf-8 -*-
"""
시점정합(point-in-time) · 상장폐지 포함 유니버스.

핵심: 각 리밸런싱 날짜 T 에서 '그때 실제로 상장돼 있던' 종목만 뽑는다.
- 현재 상장: fdr.StockListing('KRX')(주식수·시총) + KRX-DESC(상장일)
- 상장폐지: fdr.StockListing('KRX-DELISTING')(상장일·폐지일·상장주식수)
→ 생존편향 제거: 지금 사라진 종목도 '그 시점엔 살아있었다'를 반영.

한계: 과거 주식수 미확보 → marcap 추정에 '현재/폐지시점 주식수'를 사용(증자/감자 오차).
"""
from __future__ import annotations
import os
import json
from datetime import datetime, timedelta

import pandas as pd
import FinanceDataReader as fdr

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
MASTER_PATH = os.path.join(DATA_DIR, "master_universe.json")

PREF_SUFFIXES = ("5", "7", "9", "K", "L", "M")  # 우선주 코드 끝(근사)


def build_master(force: bool = False) -> pd.DataFrame:
    """전체(현재+폐지) 종목 마스터. code,name,market,is_common,listing_date,
    delisting_date(None=현재상장),shares."""
    if os.path.exists(MASTER_PATH) and not force:
        return pd.read_json(MASTER_PATH, dtype={"code": str})

    # 현재 상장 (주식수/시장)
    krx = fdr.StockListing("KRX")
    krx_shares = {}
    for _, r in krx.iterrows():
        c = str(r["Code"]).zfill(6)
        krx_shares[c] = {"name": r["Name"], "market": r["Market"],
                         "shares": r.get("Stocks")}
    # 상장일 + 업종
    desc = fdr.StockListing("KRX-DESC")
    listing_date = {str(r["Code"]).zfill(6): r["ListingDate"]
                    for _, r in desc.iterrows()}
    industry = {str(r["Code"]).zfill(6): r.get("Industry")
                for _, r in desc.iterrows()}

    rows = []
    for c, v in krx_shares.items():
        rows.append({
            "code": c, "name": v["name"], "market": v["market"],
            "is_common": _is_common(c, None, v["name"]),
            "listing_date": _d(listing_date.get(c)),
            "delisting_date": None,
            "shares": _num(v["shares"]),
            "industry": _s(industry.get(c)),
        })

    # 상장폐지 종목
    dl = fdr.StockListing("KRX-DELISTING")
    active = set(krx_shares.keys())
    for _, r in dl.iterrows():
        c = str(r["Symbol"]).zfill(6)
        if c in active:
            continue  # 재상장 등 중복 → 현재상장 우선
        rows.append({
            "code": c, "name": r["Name"], "market": r["Market"],
            "is_common": _is_common(c, r.get("SecuGroup"), r["Name"]),
            "listing_date": _d(r.get("ListingDate")),
            "delisting_date": _d(r.get("DelistingDate")),
            "shares": _num(r.get("ListingShares")),
            "industry": _s(r.get("Industry")),
        })

    df = pd.DataFrame(rows)
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_json(MASTER_PATH, force_ascii=False)
    return df


def eligible_at(master: pd.DataFrame, date: str, cfg) -> pd.DataFrame:
    """날짜(date='YYYY-MM-DD')에 상장돼 있던 적격 종목(시총필터 前). 가격/시총은 별도."""
    t = pd.Timestamp(date)
    m = master
    listed = m["listing_date"].notna() & (pd.to_datetime(m["listing_date"]) <=
                                          t - pd.Timedelta(days=cfg.MIN_LISTING_DAYS))
    dd = pd.to_datetime(m["delisting_date"], errors="coerce")
    not_delisted = dd.isna() | (dd > t)     # 아직 상장 중
    in_mkt = m["market"].isin(cfg.MARKETS)
    common = m["is_common"] if cfg.COMMON_STOCK_ONLY else True
    name_ok = ~m["name"].astype(str).apply(
        lambda n: any(kw in n for kw in cfg.NAME_EXCLUDE_KEYWORDS))
    out = m[listed & not_delisted & in_mkt & common & name_ok].copy()
    return out.reset_index(drop=True)


def _is_common(code: str, secugroup, name) -> bool:
    if secugroup is not None and str(secugroup) != "nan":
        return str(secugroup) == "주권"
    n = str(name)
    if n.endswith(("우", "우B", "우C")):
        return False
    return str(code).endswith("0")


def _d(v):
    if v is None:
        return None
    s = str(v)
    if s in ("", "nan", "NaT", "None"):
        return None
    return s[:10]


def _num(v):
    try:
        if v is None or str(v) in ("", "nan"):
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _s(v):
    if v is None:
        return None
    s = str(v)
    return None if s in ("", "nan", "None", "NaT") else s
