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


def _perf_context(conn, tmap, master):
    """모든 테마 구성종목의 최근 수익률·시총 맵 계산 (한 번만)."""
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
        ret[c] = ((cl[0] / cl[21] - 1) if len(cl) >= 22 and cl[21] else None,
                  (cl[0] / cl[63] - 1) if len(cl) >= 64 and cl[63] else None)
        if shares.get(c):
            marcap[c] = shares[c] * cl[0]
    return ret, marcap


def _perf_for(codes, ret, marcap, top_n=10):
    """codes 중 가격 있는 것을 시총 상위 top_n 골라 동일가중 수익률."""
    priced = [c for c in set(codes) if c in ret]
    priced.sort(key=lambda c: marcap.get(c, 0), reverse=True)
    top = priced[:top_n]
    r1s = [ret[c][0] for c in top if ret[c][0] is not None]
    r3s = [ret[c][1] for c in top if ret[c][1] is not None]
    return {
        "priced": len(priced), "used": len(r1s),
        "ret_1m": round(sum(r1s) / len(r1s) * 100, 1) if r1s else None,
        "ret_3m": round(sum(r3s) / len(r3s) * 100, 1) if r3s else None,
    }


def _ctx(conn, tmap, master):
    if tmap is None:
        tmap = load_theme_map()
    if master is None:
        from factor.universe import build_master
        master = build_master()
    return tmap, master, _perf_context(conn, tmap, master)


def compute_theme_perf(conn, tmap=None, master=None, top_n=10):
    """테마(소그룹)별 시총상위 top_n 동일가중 수익률."""
    tmap, master, (ret, marcap) = _ctx(conn, tmap, master)
    out = []
    for no, t in tmap["themes"].items():
        p = _perf_for(t["codes"], ret, marcap, top_n)
        out.append({"no": no, "name": t["name"], "count": len(t["codes"]), **p})
    return out


def compute_group_hierarchy(conn, tmap=None, master=None, top_n=10):
    """대그룹 → 중그룹 → 소그룹(테마) 3단계 + 각 레벨 시총상위 top_n 수익률."""
    from factor.theme_groups import classify
    tmap, master, (ret, marcap) = _ctx(conn, tmap, master)
    # 소그룹(테마) 단위 정보 + 그룹 태깅
    mids = {}          # (major,mid) -> {codes:set, themes:[...]}
    for no, t in tmap["themes"].items():
        major, mid = classify(t["name"])
        m = mids.setdefault((major, mid), {"codes": set(), "themes": []})
        m["codes"].update(t["codes"])
        tp = _perf_for(t["codes"], ret, marcap, top_n)
        m["themes"].append({"no": no, "name": t["name"],
                            "count": len(t["codes"]), **tp})
    # 대그룹 집계
    majors = {}
    for (major, mid), m in mids.items():
        mid_perf = _perf_for(m["codes"], ret, marcap, top_n)
        m["themes"].sort(key=lambda x: (x["ret_1m"] is not None, x["ret_1m"]),
                         reverse=True)
        maj = majors.setdefault(major, {"codes": set(), "mids": []})
        maj["codes"].update(m["codes"])
        maj["mids"].append({"mid": mid, **mid_perf,
                            "theme_count": len(m["themes"]), "themes": m["themes"]})
    out = []
    for major, maj in majors.items():
        maj_perf = _perf_for(maj["codes"], ret, marcap, top_n)
        maj["mids"].sort(key=lambda x: (x["ret_1m"] is not None, x["ret_1m"]),
                         reverse=True)
        out.append({"major": major, **maj_perf, "mids": maj["mids"]})
    out.sort(key=lambda x: (x["ret_1m"] is not None, x["ret_1m"]), reverse=True)
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
