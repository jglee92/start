# -*- coding: utf-8 -*-
"""
파라미터 민감도 스윕 (2단계 튜닝).

청산 조합(손절 · 익절 · 보유기간)을 훑어 '왕복 비용을 넘는 robust한 설정'이
있는지 확인한다. 신호(진입)는 스크리닝 파라미터로 고정 → 한 번만 계산하고
청산 조합만 바꿔 재평가하므로 빠르다.

⚠️ 과최적화 경계: 표본 전체에서 가장 좋은 하나를 고르지 말 것. 여러 인접 조합이
   함께 비용을 넘어야(=평탄한 고지) 신뢰할 수 있다. 하나만 튀면 그건 노이즈.
"""
from __future__ import annotations
import sys
import statistics as st

sys.stdout.reconfigure(encoding="utf-8")

import config as cfg
import db
from bt_run import load_panel, compute_features, is_signal, simulate_exit

# 스윕 격자
STOP_GRID = [None, -10.0, -7.0, -5.0, -4.0, -3.0]   # None = 손절 없음
TAKE_GRID = [None, 15.0, 10.0, 7.0, 5.0]            # None = 익절 없음
HOLD_GRID = [1, 2, 3, 5, 10]

ROUND_TRIP = (cfg.BT_FEE_RATE * 2 + cfg.BT_SELL_TAX + cfg.BT_SLIPPAGE * 2) * 100


def build_signals(panel):
    """모든 신호 진입점 (rows, entry_idx) 리스트. 청산 조합과 무관하게 고정."""
    entries = []
    for code, rows in panel.items():
        if len(rows) < cfg.VOL_LOOKBACK + max(HOLD_GRID) + 5:
            continue
        compute_features(rows)
        for i in range(len(rows) - 1):
            if is_signal(rows[i]):
                entries.append((rows, i + 1))
    return entries


def evaluate(entries, tp, sl, hold):
    nets = []
    for rows, ei in entries:
        res = simulate_exit(rows, ei, take_profit=tp, stop_loss=sl, hold_days=hold)
        if res is None:
            continue
        nets.append(res[1])  # net %
    if not nets:
        return None
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float('inf')
    return {"n": len(nets), "win": len(wins) / len(nets) * 100,
            "avg": st.mean(nets), "med": st.median(nets), "pf": pf}


def main():
    conn = db.connect()
    panel = load_panel(conn)
    conn.close()
    if not panel:
        print("daily_prices 비어있음. 먼저 bt_fetch.py 실행.")
        return

    entries = build_signals(panel)
    print(f"신호 진입점 {len(entries)}개 · 왕복비용 {ROUND_TRIP:.2f}%")
    print(f"스윕: 손절{STOP_GRID} × 익절{TAKE_GRID} × 보유{HOLD_GRID}\n")

    results = []
    for sl in STOP_GRID:
        for tp in TAKE_GRID:
            for hold in HOLD_GRID:
                r = evaluate(entries, tp, sl, hold)
                if r:
                    r.update({"sl": sl, "tp": tp, "hold": hold})
                    results.append(r)

    # net 평균 기준 상위
    results.sort(key=lambda r: r["avg"], reverse=True)
    print(f"{'손절':>5} {'익절':>5} {'보유':>4} | {'n':>5} {'승률':>6} "
          f"{'net평균':>8} {'중앙':>7} {'PF':>5}")
    print("-" * 60)
    for r in results[:20]:
        sl = "없음" if r["sl"] is None else f"{r['sl']:.0f}"
        tp = "없음" if r["tp"] is None else f"{r['tp']:.0f}"
        flag = " ★" if r["avg"] > 0 else ""
        print(f"{sl:>5} {tp:>5} {r['hold']:>4} | {r['n']:>5} {r['win']:>5.1f}% "
              f"{r['avg']:>+7.2f}% {r['med']:>+6.2f}% {r['pf']:>5.2f}{flag}")

    pos = [r for r in results if r["avg"] > 0]
    print(f"\nnet 평균 > 0 인 조합: {len(pos)}/{len(results)}")
    if not pos:
        print(">> 어떤 조합도 비용을 넘지 못함. 이 스크리닝은 실매매 부적합(현 상태).")
    elif len(pos) < 3:
        print(">> 흑자 조합이 극소수 → 과최적화(노이즈) 의심. robust 하지 않음.")
    else:
        print(">> 흑자 조합이 다수. 인접 조합들이 함께 흑자인지(평탄한 고지) 확인 필요.")
    print("\n한계: 생존편향 · 상폐 미반영 → 실제는 이보다 나쁨. 낙관 상단으로 해석.")


if __name__ == "__main__":
    main()
