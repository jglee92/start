# -*- coding: utf-8 -*-
"""매 영업일 아침 파이프라인 자가 점검 — 2026-07 사고(배포DB 100MB 초과로 daily-prices/
daily-fundamentals의 git push가 5일간 조용히 실패, 그동안 콘텐츠는 옛 데이터로 계속
'성공' 발행)를 계기로 추가. 그때 진짜 문제는 "뭔가 잘못돼도 큰 소리로 알려주는 장치가
없었다"는 것 — GitHub Actions가 매일 '실패'로 떴지만 아무도 못 봤다.

이 스크립트는 그날 겪은 실패 모드를 전부 점검한다:
  1) 배포DB 파일/용량(100MB 근접 경보 — 초과하면 push가 막힘)
  2) 라이브 사이트 기준일(asof)이 배포DB 최신일을 반영하는지
  3) 배포DB 시세가 '기대 최근 거래일'만큼 최신인지(휴장 캘린더 반영)
  4) 오늘자 콘텐츠(블로그·카드·insight)가 실제로 생성·커밋됐는지
  5) 핵심 워크플로우(가격·재무·콘텐츠) 최근 실행이 성공했는지(푸시 실패 즉시 감지)

결과는 GitHub Actions Job Summary에 항상 남기고, 문제가 있으면 health-alert 라벨
이슈로 알린다(열린 이슈 있으면 코멘트, 없으면 생성 — 중복 방지). critical이면 워크플로우도
실패(빨강) 처리해 이중 신호."""
from __future__ import annotations
import json
import os
import subprocess
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8")

KST = timezone(timedelta(hours=9))
DB_PATH = os.getenv("KR_DB_PATH", "data/screener_deploy.db")
SITE = os.getenv("SITE_BASE_URL", "https://getmoneycheckup.com").rstrip("/")
# 문제 감지 시 이메일 알림 수신자. 발신은 뉴스레터와 같은 검증 도메인(getmoneycheckup.com)을
# 재사용한다(Resend는 검증된 도메인에서만 발송 가능).
ALERT_EMAIL = "whdrmsskfk92@gmail.com"
FROM_ADDR = "머니체크업 헬스체크 <news@getmoneycheckup.com>"

problems = []   # (severity, message) — severity: "critical" | "warn"
notes = []      # 정상/참고 라인


def crit(msg):
    problems.append(("critical", msg))


def warn(msg):
    problems.append(("warn", msg))


def _http_json(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": "mc-healthcheck"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _esc_html(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _send_email_alert(subject, html):
    """문제 감지 시 Resend로 알림 메일 발송(뉴스레터와 같은 API키·검증 도메인 재사용).
    RESEND_API_KEY 미설정이면 조용히 스킵 — 이메일이 안 가도 이슈·Job Summary는 남는다.
    발송은 urllib이 아니라 requests로 한다 — Resend API가 Cloudflare 뒤에 있어 urllib
    기본 UA(Python-urllib)는 403(error 1010)으로 차단당함(실제로 겪음). send_newsletter.py가
    requests로 정상 발송되는 것과 동일하게 맞춘다."""
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        print("::warning::RESEND_API_KEY 미설정 — 이메일 알림 스킵(이슈/Job Summary는 정상).")
        return
    try:
        import requests
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": FROM_ADDR, "to": [ALERT_EMAIL], "subject": subject, "html": html},
            timeout=30)
        if r.status_code >= 300:
            print(f"::warning::이메일 알림 실패: HTTP {r.status_code} {r.text[:300]}")
        else:
            print(f"이메일 알림 발송 완료 → {ALERT_EMAIL}")
    except Exception as e:
        print(f"::warning::이메일 알림 실패: {type(e).__name__}: {e}")


now = datetime.now(KST)

# 이메일 채널 검증용 — `--test-email`로 실행하면 실제 점검 없이 테스트 메일 1통만 보내고 끝낸다
# (workflow_dispatch로 한 번 눌러 수신 확인용). 정상/예약 실행엔 이 인자가 없으므로 무영향.
if "--test-email" in sys.argv:
    _send_email_alert(
        f"[헬스체크] 이메일 알림 테스트 {now:%Y-%m-%d %H:%M} KST",
        "<h2>✅ 헬스체크 이메일 알림이 정상 연결됐습니다</h2>"
        "<p>이 주소로 파이프라인 이상(콘텐츠 미발행·시세 정지·DB 용량 초과 등) 감지 시 "
        "알림이 옵니다. 이건 연결 확인용 테스트 메일이에요.</p>"
        "<p style='color:#999;font-size:12px'>머니체크업 자동 헬스체크 · health-check.yml</p>")
    sys.exit(0)

# 휴장 캘린더는 app의 단일 소스(_is_market_holiday + KR_MARKET_HOLIDAYS_2026)를 재사용한다.
# app import 자체가 실패하면 사이트가 못 뜬다는 뜻이라 그 자체가 critical.
_holidays = None
try:
    import app as _A
    _holidays = set(_A.KR_MARKET_HOLIDAYS_2026)
except Exception as e:
    crit(f"app.py import 실패 — 사이트 자체가 안 뜰 수 있음: {type(e).__name__}: {e}")


def _is_holiday_date(d):
    """d(date)가 휴장일(주말+공휴일)인지."""
    if d.weekday() >= 5:
        return True
    return _holidays is not None and d.strftime("%Y-%m-%d") in _holidays


def _content_expected(d):
    """그날 콘텐츠가 생성됐어야 하는가 — 일요일과 평일 공휴일엔 안 만듦.
    토요일은 '주간 마무리' 콘텐츠를 만들므로 기대 대상."""
    if d.weekday() == 6:            # 일요일
        return False
    if d.weekday() < 5 and _holidays is not None and d.strftime("%Y-%m-%d") in _holidays:
        return False               # 평일 공휴일
    return True


# ── 1) 배포DB 파일/용량 + 최신 시세일 ──────────────────────────────────────
db_max = None
if not os.path.isfile(DB_PATH):
    crit(f"배포DB 파일 없음: {DB_PATH}")
else:
    size_mb = os.path.getsize(DB_PATH) / 1e6
    try:
        conn = sqlite3.connect(DB_PATH)
        db_max = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
        conn.close()
    except Exception as e:
        crit(f"배포DB 조회 실패: {type(e).__name__}: {e}")
    notes.append(f"배포DB: 최신 시세일 {db_max} · 용량 {size_mb:.1f}MB")
    if size_mb >= 95:
        crit(f"배포DB 용량 {size_mb:.1f}MB — GitHub 100MB 제한 근접(초과하면 매일 push가 막힘). "
             f"update_data.py 보존기간·VACUUM 점검 필요.")
    elif size_mb >= 90:
        warn(f"배포DB 용량 {size_mb:.1f}MB — 100MB 여유가 줄어듦, 주시 필요.")

# ── 2) 라이브 사이트 기준일(asof)이 배포DB를 반영하는지 ─────────────────────
live_asof = None
try:
    data = _http_json(f"{SITE}/api/ranking?limit=1")
    live_asof = data.get("asof")
    notes.append(f"라이브 사이트 기준일(asof): {live_asof}")
    if db_max and live_asof and live_asof < db_max:
        crit(f"라이브 기준일({live_asof})이 배포DB({db_max})보다 과거 — 서버가 최신 데이터를 "
             f"아직 반영 못 함(재배포/캐시 갱신 확인).")
except Exception as e:
    crit(f"라이브 사이트 응답 없음({SITE}): {type(e).__name__}: {e}")

# ── 3) 시세 신선도 — 기대 최근 거래일과 비교 ────────────────────────────────
# 아침 실행 기준 '오늘' 종가는 아직 DB에 없으므로, 어제 이전의 가장 최근 거래일이 기대치.
if db_max and _holidays is not None:
    probe = now.date() - timedelta(days=1)
    for _ in range(14):
        if not _is_holiday_date(probe):
            break
        probe -= timedelta(days=1)
    expected_max = probe.strftime("%Y-%m-%d")
    if db_max < expected_max:
        crit(f"배포DB 시세가 낡음 — 최신 {db_max}, 기대 최근 거래일 {expected_max}. "
             f"일일 가격 갱신(daily-prices) 실패 가능성.")
    else:
        notes.append(f"시세 신선도 OK (기대 최근 거래일 {expected_max})")

# ── 4) 오늘자 콘텐츠 생성/커밋 여부 ─────────────────────────────────────────
today = now.date()
if _content_expected(today):
    day_dir = os.path.join("content_out", today.strftime("%Y-%m-%d"))
    if not os.path.isdir(day_dir):
        crit(f"오늘({today}) 콘텐츠 폴더 없음 — 블로그·카드 생성/커밋 실패 가능성(daily-content).")
    else:
        if not os.path.isfile(os.path.join(day_dir, "blog_draft.txt")):
            crit(f"오늘({today}) blog_draft.txt 없음.")
        cards_dir = os.path.join(day_dir, "cards")
        n_png = len([f for f in os.listdir(cards_dir) if f.lower().endswith(".png")]) \
            if os.path.isdir(cards_dir) else 0
        if n_png < 5:
            crit(f"오늘({today}) 카드뉴스 {n_png}장(5장 기대) — 카드 생성 이상.")
        if not os.path.isfile(os.path.join(day_dir, "insight.txt")):
            warn(f"오늘({today}) insight.txt(사이트 Claude 브리핑) 없음 — Claude 실패로 사이트가 "
                 f"룰베이스로 폴백 중일 수 있음(API 크레딧/키 점검).")
        if not problems or all(p[0] == "warn" for p in problems):
            notes.append(f"오늘({today}) 콘텐츠 폴더 확인 완료 (카드 {n_png}장)")
        else:
            notes.append(f"오늘({today}) 콘텐츠 폴더 존재 (카드 {n_png}장)")
else:
    notes.append(f"오늘({today})은 휴장/일요일 — 콘텐츠 검사 생략")

# ── 5) 핵심 워크플로우 최근 실행 결과(푸시 실패 즉시 감지) ──────────────────
def _latest_run(wf):
    try:
        out = subprocess.check_output(
            ["gh", "run", "list", "--workflow", wf, "--limit", "1",
             "--json", "conclusion,status,displayTitle"], text=True, encoding="utf-8")
        arr = json.loads(out)
        return arr[0] if arr else None
    except Exception as e:
        return {"_err": str(e)}


for wf in ["daily-prices.yml", "daily-fundamentals.yml", "daily-content.yml"]:
    r = _latest_run(wf)
    if r is None:
        continue
    if r.get("_err"):
        notes.append(f"{wf} 최근 실행 조회 실패: {r['_err']}")
        continue
    if r.get("status") != "completed":
        notes.append(f"{wf} 최근 실행 진행 중({r.get('status')}) — 스킵")
        continue
    concl = r.get("conclusion")
    if concl != "success":
        crit(f"{wf} 최근 실행 결과 '{concl}' — 실패 원인 확인 필요: {r.get('displayTitle', '')}")
    else:
        notes.append(f"{wf} 최근 실행: success")

# ── 요약(Job Summary) ──────────────────────────────────────────────────────
crits = [m for s, m in problems if s == "critical"]
warns = [m for s, m in problems if s == "warn"]
ts = now.strftime("%Y-%m-%d %H:%M KST")
lines = []
if crits:
    lines.append(f"## \U0001F534 헬스체크 이상 감지 ({ts})")
    lines += [f"- \U0001F534 {m}" for m in crits]
    lines += [f"- \U0001F7E1 {m}" for m in warns]
elif warns:
    lines.append(f"## \U0001F7E1 헬스체크 경고 ({ts})")
    lines += [f"- \U0001F7E1 {m}" for m in warns]
else:
    lines.append(f"## ✅ 헬스체크 정상 ({ts})")
lines.append("")
lines.append("<details><summary>점검 상세</summary>")
lines.append("")
lines += [f"- {n}" for n in notes]
lines.append("")
lines.append("</details>")
summary = "\n".join(lines)
print(summary)
gsp = os.environ.get("GITHUB_STEP_SUMMARY")
if gsp:
    with open(gsp, "a", encoding="utf-8") as f:
        f.write(summary + "\n")

# ── 문제 있을 때만 알림: GitHub 이슈 + 이메일(Resend) ──────────────────────
if crits or warns:
    title = (f"[헬스체크] {now:%Y-%m-%d} 파이프라인 이상 {len(crits)}건"
             if crits else f"[헬스체크] {now:%Y-%m-%d} 경고 {len(warns)}건")

    # (a) GitHub 이슈 — 열린 health-alert 이슈 있으면 코멘트, 없으면 생성(중복 방지)
    if os.environ.get("GH_TOKEN"):
        body = summary + "\n\n_자동 생성 · health-check.yml_"
        try:
            existing = json.loads(subprocess.check_output(
                ["gh", "issue", "list", "--label", "health-alert", "--state", "open",
                 "--json", "number", "--limit", "1"], text=True, encoding="utf-8") or "[]")
            if existing:
                subprocess.run(["gh", "issue", "comment", str(existing[0]["number"]),
                                "--body", body], check=False)
            else:
                subprocess.run(["gh", "issue", "create", "--title", title, "--body", body,
                                "--label", "health-alert"], check=False)
        except Exception as e:
            print(f"::warning::이슈 알림 실패: {e}")

    # (b) 이메일 알림(Resend)
    hue = "#b60205" if crits else "#b58900"
    hb = [f'<h2 style="color:{hue};margin:0 0 10px">'
          f'{"🔴 파이프라인 이상 감지" if crits else "🟡 헬스체크 경고"} · {_esc_html(ts)}</h2>', "<ul>"]
    hb += [f'<li style="margin:4px 0"><b>🔴</b> {_esc_html(m)}</li>' for m in crits]
    hb += [f'<li style="margin:4px 0">🟡 {_esc_html(m)}</li>' for m in warns]
    hb.append("</ul>")
    hb.append('<hr><p style="color:#666;font-size:13px;margin:8px 0 4px">점검 상세</p>'
              '<ul style="color:#666;font-size:13px">')
    hb += [f"<li>{_esc_html(n)}</li>" for n in notes]
    hb.append("</ul>")
    hb.append('<p style="color:#999;font-size:12px">머니체크업 자동 헬스체크 · '
              'GitHub Actions health-check.yml</p>')
    _send_email_alert(title, "\n".join(hb))

if crits:
    sys.exit(1)
