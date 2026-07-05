# -*- coding: utf-8 -*-
"""
백테스트 엔진 (2단계).

daily_prices 패널에서 과거일별로 스크리닝을 재현(no look-ahead)하고,
D+1 시가 매수 → 익절/손절/시간청산, 비용(수수료+거래세+슬리피지) 차감 후
성과를 낸다. 핵심 질문: '스크리닝이 유니버스 평균보다 나은가?'

가격 스크리닝만 검증한다(DART 재무필터는 과거 시점 재무 부재로 v1 제외).
"""
from __future__ import annotations
import sys
import statistics as st

sys.stdout.reconfigure(encoding="utf-8")

import config as cfg
import db


def load_panel(conn):
    """daily_prices -> {code: [rows...]}, 각 row=dict(date,open,high,low,close,volume)."""
    cur = conn.execute(
        "SELECT code,date,open,high,low,close,volume FROM daily_prices "
        "ORDER BY code, date")
    panel: dict[str, list] = {}
    for code, date, o, h, l, c, v in cur:
        if o is None or c is None or h is None or l is None:
            continue
        panel.setdefault(code, []).append(
            {"date": date, "open": o, "high": h, "low": l, "close": c,
             "volume": v or 0})
    return panel


def compute_features(rows):
    """각 봉에 change_ratio, high_ret, close_strength, vol_mult, amount 부여."""
    n = len(rows)
    for i in range(n):
        r = rows[i]
        o, h, l, c = r["open"], r["high"], r["low"], r["close"]
        r["amount"] = c * r["volume"]
        r["high_ret"] = (h / o - 1) * 100 if o else 0.0
        rng = h - l
        r["cstr"] = 1.0 if rng <= 0 else max(0.0, min(1.0, (c - l) / rng))
        r["chg"] = ((c / rows[i - 1]["close"] - 1) * 100
                    if i > 0 and rows[i - 1]["close"] else None)
        # 직전 VOL_LOOKBACK 평균(오늘 제외)
        if i > cfg.VOL_LOOKBACK:
            prior = [rows[k]["volume"] for k in range(i - cfg.VOL_LOOKBACK, i)]
            avg = sum(prior) / len(prior)
            r["vmult"] = r["volume"] / avg if avg > 0 else None
        else:
            r["vmult"] = None
    return rows


def is_signal(r) -> bool:
    if r["chg"] is None or r["vmult"] is None:
        return False
    if r["amount"] < cfg.MIN_TRADING_VALUE:
        return False
    if r["chg"] < cfg.MIN_CLOSE_RET:
        return False
    if r["vmult"] < cfg.VOL_SURGE_MULT:
        return False
    if r["chg"] >= cfg.SURGE_CLOSE_PCT:
        return True
    if r["high_ret"] >= cfg.SURGE_HIGH_PCT and r["cstr"] >= cfg.MIN_CLOSE_STRENGTH:
        return True
    return False


_USE_CFG = object()   # '미지정' 센티넬 (None 은 '해당 청산 비활성'을 의미)


def simulate_exit(rows, entry_idx, take_profit=_USE_CFG, stop_loss=_USE_CFG,
                  hold_days=_USE_CFG, stop_first=_USE_CFG):
    """entry_idx = 매수일(=신호 다음날) 위치. (gross_ret%, net_ret%, exit_kind) 반환.

    take_profit/stop_loss 를 명시적으로 None 으로 주면 해당 청산 미적용(no-TP / no-stop).
    인자를 아예 안 주면(_USE_CFG) config 기본값 사용.
    """
    if take_profit is _USE_CFG:
        take_profit = cfg.BT_TAKE_PROFIT
    if stop_loss is _USE_CFG:
        stop_loss = cfg.BT_STOP_LOSS
    if hold_days is _USE_CFG:
        hold_days = cfg.BT_HOLD_DAYS
    if stop_first is _USE_CFG:
        stop_first = cfg.BT_STOP_FIRST_ON_TIE

    entry_open = rows[entry_idx]["open"]
    if not entry_open:
        return None
    tp = entry_open * (1 + take_profit / 100) if take_profit is not None else None
    sl = entry_open * (1 + stop_loss / 100) if stop_loss is not None else None
    last = min(entry_idx + hold_days - 1, len(rows) - 1)

    exit_price, kind = None, "time"
    for j in range(entry_idx, last + 1):
        hi, lo = rows[j]["high"], rows[j]["low"]
        hit_sl = sl is not None and lo <= sl
        hit_tp = tp is not None and hi >= tp
        if hit_sl and hit_tp:
            exit_price, kind = (sl, "stop") if stop_first else (tp, "take")
            break
        if hit_sl:
            exit_price, kind = sl, "stop"
            break
        if hit_tp:
            exit_price, kind = tp, "take"
            break
    if exit_price is None:
        exit_price, kind = rows[last]["close"], "time"

    gross = (exit_price / entry_open - 1) * 100
    buy = entry_open * (1 + cfg.BT_SLIPPAGE + cfg.BT_FEE_RATE)
    sell = exit_price * (1 - cfg.BT_SLIPPAGE - cfg.BT_FEE_RATE - cfg.BT_SELL_TAX)
    net = (sell / buy - 1) * 100
    return gross, net, kind


def fixed_horizon_ret(rows, entry_idx):
    """매수일 시가 -> BT_HOLD_DAYS 거래일 뒤 종가 (gross %). 비교 기준용."""
    sell_idx = entry_idx + cfg.BT_HOLD_DAYS - 1
    if sell_idx >= len(rows):
        return None
    o = rows[entry_idx]["open"]
    c = rows[sell_idx]["close"]
    if not o:
        return None
    return (c / o - 1) * 100


def stats(name, arr):
    if not arr:
        print(f"  {name}: (표본 없음)")
        return
    wins = [x for x in arr if x > 0]
    losses = [x for x in arr if x <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float('inf')
    print(f"  {name}: n={len(arr):>5} · 승률 {len(wins)/len(arr)*100:5.1f}% · "
          f"평균 {st.mean(arr):+6.2f}% · 중앙 {st.median(arr):+6.2f}% · PF {pf:4.2f}")


def main():
    conn = db.connect()
    panel = load_panel(conn)
    conn.close()
    if not panel:
        print("daily_prices 가 비어있습니다. 먼저 `python bt_fetch.py` 실행.")
        return

    print(f"패널 {len(panel)}종목 로드. 백테스트 실행...\n")

    sig_gross, sig_net, sig_fixed, kinds = [], [], [], []
    baseline_fixed = []

    for code, rows in panel.items():
        if len(rows) < cfg.VOL_LOOKBACK + cfg.BT_HOLD_DAYS + 5:
            continue
        compute_features(rows)
        for i in range(len(rows) - 1):
            entry_idx = i + 1  # 신호 다음날 매수
            # 기준선: 모든 종목-일의 고정보유 수익 (유니버스 드리프트)
            fh_all = fixed_horizon_ret(rows, entry_idx)
            if fh_all is not None:
                baseline_fixed.append(fh_all)
            # 신호일만 매매
            if not is_signal(rows[i]):
                continue
            res = simulate_exit(rows, entry_idx)
            if res is None:
                continue
            g, nt, kind = res
            sig_gross.append(g)
            sig_net.append(nt)
            kinds.append(kind)
            fh = fixed_horizon_ret(rows, entry_idx)
            if fh is not None:
                sig_fixed.append(fh)

    print("===== 백테스트 결과 =====")
    print(f"규칙: D+1 시가 매수 · 익절 {cfg.BT_TAKE_PROFIT}% / 손절 {cfg.BT_STOP_LOSS}% / "
          f"최대 {cfg.BT_HOLD_DAYS}거래일 보유")
    print(f"비용: 수수료 {cfg.BT_FEE_RATE*100:.3f}%×2 + 거래세 {cfg.BT_SELL_TAX*100:.2f}% + "
          f"슬리피지 {cfg.BT_SLIPPAGE*100:.2f}%×2 (왕복 ≈ "
          f"{(cfg.BT_FEE_RATE*2+cfg.BT_SELL_TAX+cfg.BT_SLIPPAGE*2)*100:.2f}%)\n")

    print("[신호 매매 — 익절/손절/시간 청산]")
    stats("총비용 반영(net)", sig_net)
    stats("비용 제외(gross)", sig_gross)
    if kinds:
        from collections import Counter
        ck = Counter(kinds)
        print(f"  청산유형: 익절 {ck.get('take',0)} · 손절 {ck.get('stop',0)} · "
              f"시간 {ck.get('time',0)}")

    print("\n[edge 비교 — 동일 고정보유(매수시가→보유후 종가), gross]")
    stats("신호 종목", sig_fixed)
    stats("유니버스 전체(기준선)", baseline_fixed)
    if sig_fixed and baseline_fixed:
        edge = st.mean(sig_fixed) - st.mean(baseline_fixed)
        print(f"\n  >> 신호 - 기준선 = {edge:+.2f}%p "
              f"({'edge 있음(gross)' if edge > 0 else 'edge 없음'})")
        print(f"     왕복 비용 ≈ {(cfg.BT_FEE_RATE*2+cfg.BT_SELL_TAX+cfg.BT_SLIPPAGE*2)*100:.2f}% "
              f"→ 이보다 커야 실제 흑자 가능")

    print("\n한계: 유니버스=오늘 상장 종목(생존편향) · DART 재무필터 미적용 · "
          "동일봉 익손절은 손절 우선 가정 · 상장폐지/거래정지 미반영")


if __name__ == "__main__":
    main()
