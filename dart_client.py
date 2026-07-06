# -*- coding: utf-8 -*-
"""
DART OpenAPI 재무 수집.

- corpCode.xml: 종목코드(6자리) <-> DART 고유번호(8자리) 매핑 (zip, 최초 1회 캐시)
- fnlttSinglAcnt: 단일회사 '주요계정' (매출액/영업이익/당기순이익/자산·부채·자본총계)

키: .env 의 DART_API_KEY (opendart.fss.or.kr 무료 발급, 하루 20,000건)
"""
from __future__ import annotations
import os
import io
import json
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional

import requests

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CORP_MAP_PATH = os.path.join(DATA_DIR, "corp_map.json")

BASE = "https://opendart.fss.or.kr/api"

# 연간 사업보고서. (분기: 11013=1Q, 11012=반기, 11014=3Q)
REPRT_ANNUAL = "11011"


class DartError(Exception):
    pass


class DartClient:
    def __init__(self, api_key: str):
        if not api_key or api_key.startswith("여기에"):
            raise DartError("DART_API_KEY 가 설정되지 않았습니다 (.env 확인).")
        self.key = api_key
        self._corp_map: Optional[dict] = None

    # ---------- corp_code 매핑 ----------
    def corp_map(self, force: bool = False) -> dict:
        if self._corp_map is not None and not force:
            return self._corp_map
        if os.path.exists(CORP_MAP_PATH) and not force:
            with open(CORP_MAP_PATH, encoding="utf-8") as f:
                self._corp_map = json.load(f)
            return self._corp_map
        self._corp_map = self._download_corp_map()
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CORP_MAP_PATH, "w", encoding="utf-8") as f:
            json.dump(self._corp_map, f, ensure_ascii=False)
        return self._corp_map

    def _download_corp_map(self) -> dict:
        r = requests.get(f"{BASE}/corpCode.xml",
                         params={"crtfc_key": self.key}, timeout=30)
        r.raise_for_status()
        # 실패 시 JSON 에러가 올 수 있음
        if r.headers.get("content-type", "").startswith("application/json"):
            raise DartError(f"corpCode 오류: {r.text[:200]}")
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        xml_bytes = zf.read(zf.namelist()[0])
        root = ET.fromstring(xml_bytes)
        mapping = {}
        for item in root.iter("list"):
            stock = (item.findtext("stock_code") or "").strip()
            corp = (item.findtext("corp_code") or "").strip()
            if stock and corp:  # 상장사만 (stock_code 있는 것)
                mapping[stock.zfill(6)] = corp
        if not mapping:
            raise DartError("corpCode 파싱 결과가 비어있음.")
        return mapping

    def corp_code(self, stock_code: str) -> Optional[str]:
        return self.corp_map().get(str(stock_code).zfill(6))

    # ---------- 재무 조회 ----------
    def get_financials(self, stock_code: str,
                       year: Optional[int] = None,
                       fs_pref=("CFS", "OFS")) -> Optional[dict]:
        """
        연간 사업보고서 주요계정. year=None 이면 작년->재작년 순 폴백.
        반환: dict(revenue, op_profit, net_income, assets, liabilities, equity,
                  debt_ratio, op_margin, year, fs_div) 또는 None(데이터 없음).
        """
        corp = self.corp_code(stock_code)
        if not corp:
            return None
        years = [year] if year else [datetime.now().year - 1,
                                      datetime.now().year - 2]
        for y in years:
            rows = self._fetch_acnt(corp, y)
            if not rows:
                continue
            for fs in fs_pref:
                fin = self._parse(rows, fs)
                if fin:
                    fin["year"] = y
                    fin["fs_div"] = fs
                    return fin
        return None

    def get_dividend_dps(self, stock_code: str, year: int) -> Optional[float]:
        """해당 회계연도 '주당 현금배당금(원)' 보통주 DPS. 없으면 None(무배당 포함)."""
        corp = self.corp_code(stock_code)
        if not corp:
            return None
        try:
            r = requests.get(f"{BASE}/alotMatter.json", params={
                "crtfc_key": self.key, "corp_code": corp,
                "bsns_year": str(year), "reprt_code": REPRT_ANNUAL}, timeout=20)
            js = r.json()
        except Exception:
            return None
        if js.get("status") != "000":
            if js.get("status") == "020":
                raise DartError("DART 사용한도 초과.")
            return None
        for row in js.get("list", []):
            se = (row.get("se") or "").replace(" ", "")
            if "주당현금배당금" in se:      # 보통주 우선(첫 행)
                v = _amt(row.get("thstrm"))
                if v is not None:
                    return v
        return 0.0    # 배당 항목 조회됐으나 현금배당 없음

    def get_disclosures(self, stock_code: str, count: int = 8, days: int = 365) -> list:
        """최근 공시 목록. DART 공식 OpenAPI(list.json) 사용 — 크롤링 아님, 합법 공식 API.
        bgn_de/end_de 미지정 시 기본 조회기간이 매우 짧아(당일 근처) 명시적으로 지정한다.
        반환 항목의 rcept_no로 원문(dsaf001/main.do?rcpNo=...) 링크 생성."""
        corp = self.corp_code(stock_code)
        if not corp:
            return []
        end = datetime.now()
        begin = end - timedelta(days=days)
        try:
            r = requests.get(f"{BASE}/list.json", params={
                "crtfc_key": self.key, "corp_code": corp,
                "bgn_de": begin.strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"),
                "page_no": "1", "page_count": str(count), "sort": "date",
                "sort_mth": "desc"}, timeout=15)
            js = r.json()
        except Exception:
            return []
        if js.get("status") == "020":
            raise DartError("DART 사용한도(20,000/일) 초과.")
        if js.get("status") != "000":
            return []
        out = []
        for row in js.get("list", []):
            rn = row.get("rcept_no")
            if not rn:
                continue
            out.append({
                "title": row.get("report_nm"), "date": row.get("rcept_dt"),
                "submitter": row.get("flr_nm"),
                "link": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rn}",
            })
        return out

    def _fetch_acnt(self, corp: str, year: int) -> Optional[list]:
        r = requests.get(f"{BASE}/fnlttSinglAcnt.json", params={
            "crtfc_key": self.key, "corp_code": corp,
            "bsns_year": str(year), "reprt_code": REPRT_ANNUAL,
        }, timeout=20)
        try:
            js = r.json()
        except Exception:
            return None
        status = js.get("status")
        if status == "000":
            return js.get("list", [])
        if status in ("013",):     # 조회 데이터 없음
            return None
        if status == "020":        # 사용한도 초과
            raise DartError("DART 사용한도(20,000/일) 초과.")
        if status in ("010", "011", "012"):  # 키/권한 문제
            raise DartError(f"DART 키 오류(status={status}): {js.get('message')}")
        return None

    def _parse(self, rows: list, fs_div: str) -> Optional[dict]:
        sub = [x for x in rows if x.get("fs_div") == fs_div]
        if not sub:
            return None

        def pick(names, sj=None):
            for x in sub:
                if sj and x.get("sj_div") != sj:
                    continue
                nm = (x.get("account_nm") or "").replace(" ", "")
                if any(n in nm for n in names):
                    return _amt(x.get("thstrm_amount"))
            return None

        revenue = pick(["매출액", "수익(매출액)", "영업수익"], sj="IS")
        op_profit = pick(["영업이익"], sj="IS")
        net_income = pick(["당기순이익"], sj="IS")
        assets = pick(["자산총계"], sj="BS")
        liabilities = pick(["부채총계"], sj="BS")
        equity = pick(["자본총계"], sj="BS")

        # 최소한 손익 또는 재무상태표 중 뭔가는 있어야 유효
        if all(v is None for v in
               [revenue, op_profit, net_income, assets, liabilities, equity]):
            return None

        debt_ratio = (liabilities / equity * 100.0
                      if liabilities is not None and equity else None)
        op_margin = (op_profit / revenue * 100.0
                     if op_profit is not None and revenue else None)
        return {
            "revenue": revenue, "op_profit": op_profit,
            "net_income": net_income, "assets": assets,
            "liabilities": liabilities, "equity": equity,
            "debt_ratio": debt_ratio, "op_margin": op_margin,
        }


def _amt(s) -> Optional[float]:
    """DART 금액 문자열 -> float. '1,234' / '-1,234' / '' 처리."""
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None
