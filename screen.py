# -*- coding: utf-8 -*-
"""
아침 스크리닝 (1단계).

파이프라인:
  1) provider 스냅샷(전 종목 EOD) 수집
  2) 유니버스 필터: 보통주 / 시장 / 유동성·시총 밴드
  3) 1차 급등 필터: 전일 등락률 or 장중 고가율
  4) 후보에 대해 히스토리 조회 -> 거래량 급증(20일 평균 대비) 계산
  5) 스코어링 -> 상위 N 워치리스트
  6) SQLite 저장 + 콘솔/CSV 출력

자동매매 아님. 어제 거래량 동반 급등한 종목의 '오늘 관심 후보'를 만든다.
"""
from __future__ import annotations
import os
import sys
import math
import csv
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import config as cfg
import db
from providers import get_provider


def in_universe(row) -> bool:
    if row["market"] not in cfg.MARKETS:
        return False
    if cfg.COMMON_STOCK_ONLY and not str(row["code"]).endswith("0"):
        return False
    name = str(row["name"])
    for kw in cfg.NAME_EXCLUDE_KEYWORDS:
        if kw in name:
            return False
    if row["amount"] < cfg.MIN_TRADING_VALUE:
        return False
    if row["marcap"] < cfg.MIN_MARKET_CAP:
        return False
    if cfg.MAX_MARKET_CAP is not None and row["marcap"] > cfg.MAX_MARKET_CAP:
        return False
    return True


def high_ret(row) -> float:
    """장중 고가 / 시가 - 1 (%). 시가 결측/0이면 0."""
    o = row["open"]
    if not o or o <= 0:
        return 0.0
    return (row["high"] / o - 1.0) * 100.0


def close_strength(row) -> float:
    """(종가-저가)/(고가-저가), 0~1. 고가 마감=1, 저가 마감=0. 변동0이면 1."""
    hi, lo, cl = row["high"], row["low"], row["close"]
    rng = hi - lo
    if rng <= 0:
        return 1.0
    return max(0.0, min(1.0, (cl - lo) / rng))


def is_surge(row) -> bool:
    # 종가 등락률 하한 미만이면(급락 마감) 무조건 제외
    if row["change_ratio"] < cfg.MIN_CLOSE_RET:
        return False
    # (A) 종가 자체가 강하게 오른 경우
    if row["change_ratio"] >= cfg.SURGE_CLOSE_PCT:
        return True
    # (B) 장중 고가율 급등 + 종가강도 확인 (급등 후 밀린 종목 배제)
    if (high_ret(row) >= cfg.SURGE_HIGH_PCT
            and close_strength(row) >= cfg.MIN_CLOSE_STRENGTH):
        return True
    return False


def vol_multiple(provider, conn, code: str, today_volume: float):
    """전일 거래량 / 직전 VOL_LOOKBACK일 평균 거래량. (오늘 봉 제외 평균)"""
    hist = provider.get_history(code, cfg.HISTORY_LOOKBACK_DAYS)
    if hist is None or len(hist) < 5:
        return None
    db.cache_history(conn, code, hist)
    if "volume" not in hist.columns:
        return None
    vols = hist["volume"].dropna()
    if len(vols) < 6:
        return None
    prior = vols.iloc[:-1].tail(cfg.VOL_LOOKBACK)  # 오늘 봉 제외
    avg = prior.mean()
    if not avg or avg <= 0:
        return None
    return float(today_volume) / float(avg)


def score(change_ratio, vol_mult, amount, cstrength) -> float:
    val_term = math.log10(max(amount, 1)) if amount else 0.0
    vm = min(float(vol_mult or 0), cfg.VOL_MULT_CAP)   # 아웃라이어 cap
    return (cfg.W_CLOSE_RET * float(change_ratio or 0)
            + cfg.W_VOL_MULT * vm * 5.0
            + cfg.W_TRADING_VALUE * val_term
            + cfg.W_CLOSE_STRENGTH * float(cstrength or 0) * 100.0)


def run():
    provider = get_provider(cfg.DATA_PROVIDER)
    print(f"[1/6] provider={provider.name} 스냅샷 수집 중...")
    snap = provider.get_market_snapshot()
    df = snap.df
    print(f"      기준일 {snap.date} · 전 종목 {len(df):,}개")

    print("[2/6] 유니버스 필터...")
    uni = df[df.apply(in_universe, axis=1)].copy()
    print(f"      유니버스 {len(uni):,}개 "
          f"(시장={cfg.MARKETS}, 거래대금≥{cfg.MIN_TRADING_VALUE/1e8:.0f}억, "
          f"시총 {cfg.MIN_MARKET_CAP/1e8:.0f}~"
          f"{(cfg.MAX_MARKET_CAP/1e8) if cfg.MAX_MARKET_CAP else float('inf'):.0f}억)")

    print("[3/6] 1차 급등 필터...")
    uni["high_ret"] = uni.apply(high_ret, axis=1)
    cand = uni[uni.apply(is_surge, axis=1)].copy()
    # 거래대금 큰 순으로 자르기 (히스토리 조회량 제한)
    cand = cand.sort_values("amount", ascending=False).head(cfg.MAX_ENRICH)
    print(f"      급등 후보 {len(cand):,}개 "
          f"(등락률≥{cfg.SURGE_CLOSE_PCT}% 또는 고가율≥{cfg.SURGE_HIGH_PCT}%)")

    conn = db.connect()
    run_id = db.create_run(conn, snap.date, provider.name, _params())
    db.save_snapshot(conn, run_id, df)

    print(f"[4/6] 거래량 급증 계산 (히스토리 {len(cand)}종목 조회)...")
    results = []
    for n, (_, row) in enumerate(cand.iterrows(), 1):
        vm = vol_multiple(provider, conn, row["code"], row["volume"])
        if vm is None:
            continue
        if vm < cfg.VOL_SURGE_MULT:
            continue
        cs = close_strength(row)
        reasons = []
        if row["change_ratio"] >= cfg.SURGE_CLOSE_PCT:
            reasons.append(f"등락{row['change_ratio']:.1f}%")
        if row["high_ret"] >= cfg.SURGE_HIGH_PCT:
            reasons.append(f"고가{row['high_ret']:.1f}%")
        reasons.append(f"거래량x{vm:.1f}")
        reasons.append(f"종강{cs:.2f}")
        results.append({
            "code": row["code"], "name": row["name"], "market": row["market"],
            "close": row["close"], "change_ratio": row["change_ratio"],
            "high_ret": row["high_ret"], "vol_mult": vm, "close_strength": cs,
            "amount": row["amount"], "marcap": row["marcap"],
            "score": score(row["change_ratio"], vm, row["amount"], cs),
            "reasons": " · ".join(reasons),
        })
        if n % 25 == 0:
            print(f"      ...{n}/{len(cand)} 조회, 통과 {len(results)}")

    results.sort(key=lambda r: r["score"], reverse=True)
    watch = results[:cfg.MAX_WATCHLIST]

    if cfg.DART_ENABLED:
        print("[5/6] DART 재무 수집 + '재무 양호' 필터...")
        watch = enrich_financials(conn, watch)
    else:
        print("[5/6] DART 비활성 — 재무 수집 건너뜀")

    print(f"[6/6] 워치리스트 {len(watch)}종목 저장...")
    db.save_watchlist(conn, run_id, watch)
    csv_path = _write_csv(snap.date, watch)
    conn.close()

    print(f"      완료. run_id={run_id}, DB={db.DB_PATH}")
    print(f"      CSV={csv_path}\n")
    _print_table(snap.date, watch)


def enrich_financials(conn, watch: list[dict]) -> list[dict]:
    """워치리스트에 DART 연간 재무를 붙이고, 선택적으로 '재무 양호' 필터를 적용."""
    from dart_client import DartClient, DartError
    key = os.getenv("DART_API_KEY", "")
    try:
        dart = DartClient(key)
        dart.corp_map()  # 최초 1회 매핑 로드/다운로드
    except DartError as e:
        print(f"      [경고] DART 사용 불가: {e}")
        print(f"      재무 없이 진행합니다.")
        return watch

    kept = []
    for i, r in enumerate(watch, 1):
        fin = db.get_cached_financials(conn, r["code"])
        if fin is None:
            try:
                fin = dart.get_financials(
                    r["code"], year=cfg.DART_YEAR,
                    fs_pref=cfg.DART_FS_DIV_PREFERENCE)
            except DartError as e:
                print(f"      [중단] {e}")
                fin = None
            if fin:
                db.save_financials(conn, r["code"], fin)
        _attach_fin(r, fin)

        if cfg.DART_APPLY_FILTER and not _fin_ok(fin):
            continue
        if fin and cfg.W_FIN_BONUS:
            r["score"] += cfg.W_FIN_BONUS * _fin_bonus(fin)
        kept.append(r)
        if i % 10 == 0:
            print(f"      ...{i}/{len(watch)} 재무 조회")

    kept.sort(key=lambda r: r["score"], reverse=True)
    return kept


def _attach_fin(r: dict, fin) -> None:
    r["debt_ratio"] = fin.get("debt_ratio") if fin else None
    r["op_margin"] = fin.get("op_margin") if fin else None
    r["op_profit"] = fin.get("op_profit") if fin else None
    r["revenue"] = fin.get("revenue") if fin else None
    r["fin_year"] = fin.get("year") if fin else None


def _fin_ok(fin) -> bool:
    if not fin:
        return False  # 필터 적용 시 재무 없으면 제외
    if cfg.FIN_REQUIRE_OP_PROFIT_POSITIVE:
        op = fin.get("op_profit")
        if op is None or op <= 0:
            return False
    dr = fin.get("debt_ratio")
    if cfg.FIN_MAX_DEBT_RATIO is not None and dr is not None and dr > cfg.FIN_MAX_DEBT_RATIO:
        return False
    if cfg.FIN_MIN_OP_MARGIN is not None:
        om = fin.get("op_margin")
        if om is None or om < cfg.FIN_MIN_OP_MARGIN:
            return False
    return True


def _fin_bonus(fin) -> float:
    """영업이익률 높고 부채비율 낮을수록 가산 (대략 -1~+2 범위)."""
    b = 0.0
    om = fin.get("op_margin")
    if om is not None:
        b += max(-1.0, min(2.0, om / 10.0))
    dr = fin.get("debt_ratio")
    if dr is not None:
        b += max(-1.0, min(1.0, (100.0 - dr) / 100.0))
    return b


def _params() -> dict:
    return {k: getattr(cfg, k) for k in dir(cfg)
            if k.isupper() and not k.startswith("_")}


def _write_csv(date: str, watch: list[dict]) -> str:
    out_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"watchlist_{date}.csv")
    cols = ["code", "name", "market", "close", "change_ratio", "high_ret",
            "vol_mult", "amount", "marcap", "score", "reasons",
            "fin_year", "revenue", "op_profit", "op_margin", "debt_ratio"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in watch:
            w.writerow({c: r.get(c) for c in cols})
    return path


def _print_table(date: str, watch: list[dict]) -> None:
    print(f"===== 아침 워치리스트 ({date} 기준) · {len(watch)}종목 =====")
    print(f"{'#':>2} {'코드':>6} {'종목명':<11} {'등락%':>6} "
          f"{'고가%':>6} {'거래량x':>6} {'거래대금억':>8} "
          f"{'영업益억':>8} {'영익률%':>6} {'부채%':>6} {'점수':>6}")
    print("-" * 92)
    for i, r in enumerate(watch, 1):
        op = r.get("op_profit")
        om = r.get("op_margin")
        dr = r.get("debt_ratio")
        print(f"{i:>2} {r['code']:>6} {str(r['name'])[:11]:<11} "
              f"{r['change_ratio']:>6.1f} {r['high_ret']:>6.1f} "
              f"{r['vol_mult']:>6.1f} {r['amount']/1e8:>8.0f} "
              f"{(op/1e8 if op is not None else float('nan')):>8.0f} "
              f"{(om if om is not None else float('nan')):>6.1f} "
              f"{(dr if dr is not None else float('nan')):>6.0f} "
              f"{r['score']:>6.1f}")
    if not watch:
        print("(조건을 만족하는 종목 없음 — config 임계값을 조정하세요)")


if __name__ == "__main__":
    run()
