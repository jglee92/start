# -*- coding: utf-8 -*-
"""
네이버 금융 '테마' 분류 수집 (실제 시장 테마: 2차전지·AI·초전도체 등).

KSIC 업종(factor.sectors)보다 '요즘 강세 테마' 파악에 적합. 한 종목이 여러 테마에 속함.
⚠️ 네이버 약관상 개인 리서치용으로만·정중하게(캐시, 주1회 갱신 권장). 상업/대량 금지.

캐시: data/naver_themes.json  { "themes": {no: {name, change, codes:[...]}},
                                "stock_themes": {code: [name,...]} }
"""
from __future__ import annotations
import os
import re
import json
import time

import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
THEME_PATH = os.path.join(DATA_DIR, "naver_themes.json")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

_LIST = "https://finance.naver.com/sise/theme.naver?page={p}"
_DETAIL = "https://finance.naver.com/sise/sise_group_detail.naver?type=theme&no={no}"
_RE_THEME = re.compile(r'sise_group_detail\.naver\?type=theme&no=(\d+)">([^<]+)</a>')
_RE_CHG = re.compile(r'type=theme&no=\d+">[^<]+</a>.*?<td class="number">\s*'
                     r'<span[^>]*>([-+]?\d+\.\d+)%', re.S)
_RE_CODE = re.compile(r'/item/main\.naver\?code=(\d{6})">([^<]+)</a>')


def build_theme_map(force: bool = False, max_pages: int = 10, delay: float = 0.25):
    if os.path.exists(THEME_PATH) and not force:
        return load_theme_map()
    themes = {}
    for p in range(1, max_pages + 1):
        try:
            r = requests.get(_LIST.format(p=p), headers=H, timeout=15)
            r.encoding = "euc-kr"
        except Exception:
            break
        found = _RE_THEME.findall(r.text)
        if not found:
            break
        for no, name in found:
            themes[no] = {"name": name.strip(), "change": None, "codes": []}
        time.sleep(delay)

    # 각 테마 구성종목 + 등락률
    for i, (no, t) in enumerate(themes.items(), 1):
        try:
            r = requests.get(_DETAIL.format(no=no), headers=H, timeout=15)
            r.encoding = "euc-kr"
            codes = _RE_CODE.findall(r.text)
            t["codes"] = sorted({c for c, _ in codes})
        except Exception:
            t["codes"] = []
        time.sleep(delay)
        if i % 30 == 0:
            print(f"  ...{i}/{len(themes)} 테마 수집", flush=True)

    stock_themes = {}
    for no, t in themes.items():
        for c in t["codes"]:
            stock_themes.setdefault(c, []).append(t["name"])

    out = {"themes": themes, "stock_themes": stock_themes}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(THEME_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return out


def load_theme_map():
    if not os.path.exists(THEME_PATH):
        return {"themes": {}, "stock_themes": {}}
    with open(THEME_PATH, encoding="utf-8") as f:
        return json.load(f)


def compute_theme_perf(conn, tmap=None, master=None, top_n=10):
    """테마별 최근 1개월(~21거래일)·3개월(~63거래일) 수익률.
    편차 축소를 위해 각 테마의 '시총 상위 top_n 종목'만 동일가중으로 계산."""
    if tmap is None:
        tmap = load_theme_map()
    if master is None:
        from factor.universe import build_master
        master = build_master()
    shares = {str(r.code).zfill(6): r.shares for r in master.itertuples(index=False)}

    needed = set()
    for t in tmap["themes"].values():
        needed.update(t["codes"])
    ret, marcap = {}, {}
    for c in needed:
        rows = conn.execute(
            "SELECT close FROM daily_prices WHERE code=? AND close IS NOT NULL "
            "ORDER BY date DESC LIMIT 64", (c,)).fetchall()
        cl = [r[0] for r in rows]
        if not cl:
            continue
        r1 = (cl[0] / cl[21] - 1) if len(cl) >= 22 and cl[21] else None
        r3 = (cl[0] / cl[63] - 1) if len(cl) >= 64 and cl[63] else None
        ret[c] = (r1, r3)
        sh = shares.get(c)
        if sh:
            marcap[c] = sh * cl[0]
    out = []
    for no, t in tmap["themes"].items():
        # 가격 있는 구성종목을 시총 상위로 정렬 → top_n
        priced = [c for c in t["codes"] if c in ret]
        priced.sort(key=lambda c: marcap.get(c, 0), reverse=True)
        top = priced[:top_n]
        r1s = [ret[c][0] for c in top if ret[c][0] is not None]
        r3s = [ret[c][1] for c in top if ret[c][1] is not None]
        out.append({
            "no": no, "name": t["name"], "count": len(t["codes"]),
            "priced": len(priced), "used": len(r1s),
            "ret_1m": round(sum(r1s) / len(r1s) * 100, 1) if r1s else None,
            "ret_3m": round(sum(r3s) / len(r3s) * 100, 1) if r3s else None,
        })
    return out


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    m = build_theme_map(force=True)
    th = m["themes"]
    print(f"테마 {len(th)}개 · 종목 매핑 {len(m['stock_themes'])}개")
    big = sorted(th.values(), key=lambda t: len(t["codes"]), reverse=True)[:10]
    for t in big:
        print(f"  {t['name']}: {len(t['codes'])}종목")
