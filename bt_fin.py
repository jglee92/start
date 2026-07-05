# -*- coding: utf-8 -*-
"""
재무 필터가 급등 스크리닝의 edge 를 키우는지 검증 (2단계).

신호를 '재무 양호(영업이익 흑자 · 부채비율 한도 내)' vs '부실/없음' 으로 나눠
이후 수익을 비교한다.

⚠️ look-ahead 편향: 과거 매매에 '현재(최신 연간)' 재무를 적용한다. 시점정합 재무가
   아니므로 결과는 낙관 상단이다. 여기서도 비용을 못 넘으면 재무로도 못 살린다는 뜻.
"""
from __future__ import annotations
import os
import sys
import statistics as st

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import config as cfg
import db
from bt_run import load_panel, compute_features, is_signal, simulate_exit, fixed_horizon_ret

ROUND_TRIP = (cfg.BT_FEE_RATE * 2 + cfg.BT_SELL_TAX + cfg.BT_SLIPPAGE * 2) * 100


def ensure_financials(conn, codes):
    """패널 종목 중 재무 캐시 없는 것만 DART 조회 후 저장."""
    from dart_client import DartClient, DartError
    try:
        dart = DartClient(os.getenv("DART_API_KEY", ""))
        dart.corp_map()
    except DartError as e:
        print(f"[경고] DART 불가: {e} → 재무 없이 진행")
        return 0
    fetched = 0
    todo = [c for c in codes if db.get_cached_financials(conn, c) is None]
    print(f"재무 미보유 {len(todo)}종목 조회 중...")
    for n, code in enumerate(todo, 1):
        fin = None
        for attempt in range(3):          # 네트워크 타임아웃은 재시도
            try:
                fin = dart.get_financials(code, year=cfg.DART_YEAR,
                                          fs_pref=cfg.DART_FS_DIV_PREFERENCE)
                break
            except DartError as e:        # 키/한도 오류는 즉시 중단
                print(f"  [중단] {e}")
                return fetched
            except Exception as e:        # ReadTimeout 등 → 재시도
                if attempt == 2:
                    print(f"  [건너뜀] {code}: {type(e).__name__}")
        if fin:
            db.save_financials(conn, code, fin)
            fetched += 1
        if n % 50 == 0:
            print(f"  ...{n}/{len(todo)} (적재 {fetched})")
    return fetched


def fin_ok(fin) -> bool:
    if not fin:
        return False
    if cfg.FIN_REQUIRE_OP_PROFIT_POSITIVE:
        op = fin.get("op_profit")
        if op is None or op <= 0:
            return False
    dr = fin.get("debt_ratio")
    if cfg.FIN_MAX_DEBT_RATIO is not None and dr is not None and dr > cfg.FIN_MAX_DEBT_RATIO:
        return False
    return True


def stats(name, arr):
    if not arr:
        print(f"  {name}: (표본 없음)")
        return None
    wins = [x for x in arr if x > 0]
    losses = [x for x in arr if x <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float('inf')
    print(f"  {name:<22} n={len(arr):>5} · 승률 {len(wins)/len(arr)*100:5.1f}% · "
          f"평균 {st.mean(arr):+6.2f}% · 중앙 {st.median(arr):+6.2f}% · PF {pf:4.2f}")
    return st.mean(arr)


def main():
    conn = db.connect()
    panel = load_panel(conn)
    if not panel:
        print("daily_prices 비어있음. 먼저 bt_fetch.py 실행.")
        return

    ensure_financials(conn, list(panel.keys()))
    fin_cache = {c: db.get_cached_financials(conn, c) for c in panel.keys()}
    conn.close()

    good_gross, bad_gross = [], []      # 고정보유 gross (edge 비교)
    good_net, bad_net = [], []          # 비용 반영 net (기본 청산)
    bad_entries = []                    # 재무부실 subset 진입점(추가 청산 검증용)
    baseline = []

    for code, rows in panel.items():
        if len(rows) < cfg.VOL_LOOKBACK + max(10, cfg.BT_HOLD_DAYS) + 5:
            continue
        compute_features(rows)
        ok = fin_ok(fin_cache.get(code))
        for i in range(len(rows) - 1):
            ei = i + 1
            fh = fixed_horizon_ret(rows, ei)
            if fh is not None:
                baseline.append(fh)
            if not is_signal(rows[i]):
                continue
            res = simulate_exit(rows, ei)
            if fh is not None:
                (good_gross if ok else bad_gross).append(fh)
            if res is not None:
                (good_net if ok else bad_net).append(res[1])
            if not ok:
                bad_entries.append((rows, ei))

    n_good = sum(1 for c in panel if fin_ok(fin_cache.get(c)))
    print(f"\n패널 {len(panel)}종목 (재무양호 {n_good}) · 왕복비용 {ROUND_TRIP:.2f}%")
    print("⚠️ look-ahead: 현재 재무를 과거에 적용 → 낙관 상단\n")

    print("[edge 비교 — 3일 고정보유, gross]")
    g = stats("급등+재무양호", good_gross)
    b = stats("급등+재무부실/없음", bad_gross)
    base = stats("유니버스 전체(기준선)", baseline)

    print("\n[실매매 — 기본청산(익절7/손절-4/3일), net]")
    stats("급등+재무양호", good_net)
    stats("급등+재무부실/없음", bad_net)

    print()
    if g is not None and base is not None:
        edge = g - base
        print(f">> 재무양호 신호 edge(gross) = {edge:+.2f}%p vs 기준선")
        if b is not None:
            print(f">> 재무양호 - 재무부실 = {g - b:+.2f}%p "
                  f"({'재무가 도움' if g > b else '재무 도움 미미/역효과'})")
        print(f">> 왕복비용 {ROUND_TRIP:.2f}% → edge 가 이보다 커야 실전 흑자 (look-ahead 감안하면 더 커야)")

    # 재무부실(투기적) subset 이 손절 없는 청산에서 비용을 넘는지 검증
    print("\n[재무부실 subset — 청산별 net 검증 (edge 실재 vs 편향 착시)]")
    for sl, tp, hold in [(None, None, 3), (None, None, 5), (None, None, 10),
                         (-10.0, 15.0, 10), (-4.0, 7.0, 3)]:
        nets = []
        for rows, ei in bad_entries:
            res = simulate_exit(rows, ei, take_profit=tp, stop_loss=sl, hold_days=hold)
            if res:
                nets.append(res[1])
        if nets:
            sls = "없음" if sl is None else f"{sl:.0f}"
            tps = "없음" if tp is None else f"{tp:.0f}"
            avg = st.mean(nets)
            print(f"  손절{sls:>4} 익절{tps:>4} 보유{hold:>2} → net평균 {avg:+.2f}% "
                  f"승률 {sum(1 for x in nets if x>0)/len(nets)*100:.1f}% "
                  f"{'★비용상회' if avg>0 else ''}")

    print("\n한계: look-ahead 재무 · 생존편향(상폐/거래정지 종목 누락) · '재무없음'엔 신규상장/"
          "스팩 다수 → 재무부실 수치는 특히 낙관 상단. 실제는 이보다 나쁨.")


if __name__ == "__main__":
    main()
