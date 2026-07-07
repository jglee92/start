# -*- coding: utf-8 -*-
"""
SUE(표준화 예상외 실적) 기반 사건-드리프트 파일럿 백테스트.

공시일 기준 순방향 N일 수익률(비용반영)을 SUE 그룹별로 비교한다.
※ 정식 캘린더타임 포트폴리오가 아닌 풀링(pooled event) 방식의 1차 탐색 분석 —
  통계적 엄밀함(중복기간 이벤트의 상관관계 등)은 부족하지만, "더 큰 표본으로 확장할
  가치가 있는가"를 빠르게 판단하기엔 충분하다.
"""
from __future__ import annotations
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db
from factor.pead import compute_sue_series
from factor.data import price_asof, price_first_after
import factor_config as cfg

RT_BUY = 1 + cfg.SLIPPAGE + cfg.FEE_RATE
RT_SELL = 1 - cfg.SLIPPAGE - cfg.FEE_RATE - cfg.SELL_TAX


def _add_days(d, days):
    y, m, dd = map(int, d.split("-"))
    return (date(y, m, dd) + timedelta(days=days)).isoformat()


def event_return(conn, code, disclosed_date, hold_days):
    """공시일 다음 최초체결가 매수 -> 공시일+hold_days 종가 매도, 비용반영."""
    b = price_first_after(conn, code, disclosed_date)
    if not b:
        return None
    sell_date = _add_days(disclosed_date, hold_days)
    s = price_asof(conn, code, sell_date)
    if not s or s[1] <= b[1]:
        return None
    buy, sell = b[0] * RT_BUY, s[0] * RT_SELL
    return sell / buy - 1


def collect_events(conn, codes, hold_days=90):
    events = []
    for code in codes:
        series = compute_sue_series(db.get_quarterly_series(conn, code))
        for r in series:
            if r.get("sue") is None or not r.get("disclosed_date"):
                continue
            ret = event_return(conn, code, r["disclosed_date"], hold_days)
            if ret is None:
                continue
            events.append({"code": code, "year": r["year"], "quarter": r["quarter"],
                           "sue": r["sue"], "disclosed_date": r["disclosed_date"], "ret": ret})
    return events


def _stdev(vals):
    if len(vals) < 2:
        return None
    m = sum(vals) / len(vals)
    return (sum((v - m) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5


def summarize(events, n_groups=5):
    if not events:
        print("이벤트 없음 (데이터 부족).")
        return
    all_rets = [e["ret"] for e in events]
    baseline = sum(all_rets) / len(all_rets) * 100
    print(f"전체 이벤트 {len(events)}건 · 전체 평균수익(베이스라인) {baseline:+.2f}%"
          f" — 이 기간엔 SUE와 무관하게 매수만 해도 이 정도는 났다는 뜻\n")

    events = sorted(events, key=lambda e: e["sue"])
    n = len(events)
    size = n // n_groups
    groups = []
    for g in range(n_groups):
        lo = g * size
        hi = (g + 1) * size if g < n_groups - 1 else n
        groups.append(events[lo:hi])

    print(f"{'그룹':>6} {'SUE범위':>18} {'건수':>5} {'평균수익%':>9} {'베이스라인差':>11} {'승률%':>7}")
    for g, grp in enumerate(groups):
        if not grp:
            continue
        rets = [e["ret"] for e in grp]
        avg = sum(rets) / len(rets) * 100
        win = sum(1 for r in rets if r > 0) / len(rets) * 100
        sue_range = f"{grp[0]['sue']:+.2f}~{grp[-1]['sue']:+.2f}"
        print(f"{g+1:>6} {sue_range:>18} {len(grp):>5} {avg:>+9.2f} {avg-baseline:>+11.2f} {win:>7.1f}")

    bot, top = groups[0], groups[-1]
    top_rets, bot_rets = [e["ret"] for e in top], [e["ret"] for e in bot]
    top_avg, bot_avg = sum(top_rets)/len(top_rets)*100, sum(bot_rets)/len(bot_rets)*100
    sd_top, sd_bot = _stdev(top_rets), _stdev(bot_rets)
    t_stat = None
    if sd_top and sd_bot:
        se = ((sd_top ** 2) / len(top_rets) + (sd_bot ** 2) / len(bot_rets)) ** 0.5
        if se:
            t_stat = ((sum(top_rets)/len(top_rets)) - (sum(bot_rets)/len(bot_rets))) / se
    print(f"\n최상위(고SUE, {len(top)}건) 평균 {top_avg:+.2f}% vs 최하위(저SUE, {len(bot)}건) 평균 {bot_avg:+.2f}%")
    line = f"롱숏 스프레드(고-저): {top_avg - bot_avg:+.2f}%p"
    if t_stat is not None:
        line += f" (Welch t-stat≈{t_stat:+.2f} — |t|>2 정도부터 참고할 만함, 이벤트간 시기 중첩 상관은 미보정)"
    print(line)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from backfill_quarterly_pilot import PILOT_CODES
    conn = db.connect()
    for hold in (60, 90):
        print("=" * 70)
        print(f"보유기간 {hold}일")
        print("=" * 70)
        events = collect_events(conn, PILOT_CODES, hold_days=hold)
        summarize(events)
        print()
    conn.close()
