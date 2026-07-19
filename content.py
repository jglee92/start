# -*- coding: utf-8 -*-
"""
SEO용 서버렌더 원본 콘텐츠 (테마 관련주 랜딩페이지 · 주간 시장 코멘터리).

스크랩 데이터를 그대로 옮기지 않고, 우리 팩터점수·밸류에이션·정렬·코멘트를 얹어
'원본 분석'으로 만든다. 크롤링 가능한 텍스트+표.
"""
from __future__ import annotations
import html
import json
from urllib.parse import urlsplit


def _esc(s):
    return html.escape(str(s if s is not None else ""))


_ICON_SVG = {
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 6 8.5 7 8.5-7"/>',
    "news": '<rect x="3.5" y="5.5" width="12" height="14" rx="1.2"/><path d="M15.5 8.5h4.2a.8.8 0 0 1 .8.8v8.2a1.8 1.8 0 0 1-1.8 1.8h-3.2"/><path d="M6.3 9h6M6.3 12h6M6.3 15h4"/>',
    "wallet": '<rect x="3.5" y="7" width="17" height="12" rx="2"/><path d="M3.5 10h17"/><circle cx="16.2" cy="14" r="1" fill="currentColor" stroke="none"/>',
    "trendUp": '<path d="M4 16l5.5-5.5 3.5 3.5L20 7"/><path d="M14.5 7H20v5.5"/>',
    "trendDown": '<path d="M4 8l5.5 5.5 3.5-3.5L20 17"/><path d="M14.5 17H20v-5.5"/>',
    "shield": '<path d="M12 3.5 18.5 6v5.5c0 4.6-2.8 7.6-6.5 8.8-3.7-1.2-6.5-4.2-6.5-8.8V6z"/>',
    "sprout": '<path d="M12 21v-9"/><path d="M12 12C7 12 5 9 5 5c5 0 7 3 7 7z"/><path d="M12 12c0-4 2-7 7-7 0 4-2 7-7 7z"/>',
    "alert": '<path d="M12 3.5 21 19.5H3z"/><path d="M12 10v3.6"/><circle cx="12" cy="16.7" r="0.9" fill="currentColor" stroke="none"/>',
    "document": '<rect x="6" y="3" width="12" height="18" rx="1.5"/><path d="M9 8h6M9 12h6M9 16h3.5"/>',
    "barchart": '<path d="M5 19V11"/><path d="M12 19V5"/><path d="M19 19v-7"/>',
    "flame": '<path d="M12 3c-1 3-4 4-4 8a4 4 0 0 0 8 0c0-1.5-.7-2.3-1.2-3.3.8.3 2.2 1.6 2.2 4.3a5 5 0 0 1-10 0c0-4 3-5 5-9z"/>',
    "gem": '<path d="M6 3h12l3 5-9 13L3 8z"/><path d="M3 8h18M9 3l-2 5 5 13 5-13-2-5"/>',
    "target": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4.2"/><circle cx="12" cy="12" r="0.8" fill="currentColor" stroke="none"/>',
    "trophy": '<path d="M7 4h10v3a5 5 0 0 1-10 0z"/><path d="M7 5H4v1a4 4 0 0 0 4 4M17 5h3v1a4 4 0 0 1-4 4"/><path d="M12 13v3M9 20h6M10 16.5h4v2.5a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1z"/>',
    "calendar": '<rect x="4" y="5.5" width="16" height="14.5" rx="1.8"/><path d="M4 10h16M8 3.5v3.5M16 3.5v3.5"/>',
    "ruler": '<path d="M4 15.5 8.5 20 20 8.5 15.5 4z"/><path d="m9 11 2 2M12 8l2 2M15 5l2 2"/>',
    "bank": '<path d="M4 9.5 12 4l8 5.5"/><path d="M5 9.5h14V19H5z"/><path d="M8 12.5V17M12 12.5V17M16 12.5V17"/><path d="M4 19h16"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 3.5v2.2M12 18.3v2.2M20.5 12h-2.2M5.7 12H3.5M17.8 6.2l-1.6 1.6M7.8 16.2l-1.6 1.6M17.8 17.8l-1.6-1.6M7.8 7.8 6.2 6.2"/>',
    "coin": '<circle cx="12" cy="12" r="8"/><path d="M9.3 14.2c.4.9 1.3 1.5 2.5 1.5 1.5 0 2.6-.9 2.6-2s-1-1.6-2.6-2c-1.5-.4-2.5-.9-2.5-2s1.1-2 2.5-2c1.2 0 2.1.6 2.5 1.5"/><path d="M12 7.3v1.2M12 15.7v1.2"/>',
    "calculator": '<rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M8 7h8"/><path d="M8 11.5h.01M12 11.5h.01M16 11.5h.01M8 15h.01M12 15h.01M16 15h.01M8 18.5h.01M12 18.5h.01M16 18.5h.01"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1" fill="currentColor" stroke="none"/><circle cx="4.5" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="4.5" cy="18" r="1" fill="currentColor" stroke="none"/>',
    "check": '<circle cx="12" cy="12" r="8"/><path d="m8.5 12.3 2.4 2.4 4.6-5.4"/>',
    "refresh": '<path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3"/><path d="M18 3v4h-4M6 21v-4h4"/>',
    "book": '<path d="M4 5.5A2 2 0 0 1 6 4h11a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H6a2 2 0 0 0-2 2z"/><path d="M4 18.5A2 2 0 0 1 6 17h12"/>',
}


def _ic(name):
    d = _ICON_SVG.get(name)
    if not d:
        return ""
    return (f'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{d}</svg>')


def _breadcrumb_ld(title, canonical):
    """홈 > 현재 페이지 2단 브레드크럼(JSON-LD) — 검색결과에 URL 대신 경로로 표시될 수 있음."""
    parts = urlsplit(canonical)
    home = f"{parts.scheme}://{parts.netloc}/"
    data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "홈", "item": home},
            {"@type": "ListItem", "position": 2, "name": title, "item": canonical},
        ],
    }
    return json.dumps(data, ensure_ascii=False)


def _fmt(v, nd=1):
    if v is None:
        return "–"
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "–"


def layout(title, desc, canonical, body, show_subscribe=True):
    parts = urlsplit(canonical)
    og_image = f"{parts.scheme}://{parts.netloc}/static/og-image.png"
    subscribe_html = f"""<!--newsletter-block-->
<div style="margin-top:28px;padding:14px 16px;border:1px solid #8883;border-radius:10px">
<div style="font-weight:700;margin-bottom:4px">{_ic('mail')} 매일 아침 국내증시 체크포인트, 이메일로 받아보기</div>
<div style="color:#4a5563;font-size:13px;margin-bottom:10px">실적발표·이상신호·강세테마 요약을 매일 아침 보내드려요.</div>
<form id="newsletterForm" style="display:flex;gap:8px;flex-wrap:wrap">
<input type="email" id="newsletterEmail" placeholder="이메일 주소" required
 style="flex:1;min-width:180px;padding:9px 12px;border-radius:7px;border:1px solid #8883">
<button type="submit" style="padding:9px 18px;border-radius:7px;border:none;background:#1a63cf;color:#fff;font-weight:700;cursor:pointer">구독하기</button>
</form>
<label style="display:flex;align-items:flex-start;gap:6px;font-size:11.5px;color:#4a5563;margin-top:8px;cursor:pointer">
<input type="checkbox" id="newsletterConsent" required style="margin-top:2px">
<span>이메일 뉴스레터 수신 및 개인정보 처리(발송 위탁: Resend)에 동의합니다.
<a href="/about#privacy">개인정보처리방침 보기</a></span>
</label>
<div id="newsletterMsg" style="font-size:12.5px;margin-top:6px"></div>
<div style="color:#4a5563;font-size:11.5px;margin-top:8px">구독 취소는 매일 받으시는 메일 맨 아래 "구독 취소" 링크로 언제든 가능합니다.</div>
</div>
<script>
document.getElementById('newsletterForm').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const email = document.getElementById('newsletterEmail').value.trim();
  const msg = document.getElementById('newsletterMsg');
  msg.style.color = '#4a5563'; msg.textContent = '처리중...';
  try {{
    const r = await fetch('/api/newsletter/subscribe', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{email}})
    }});
    if (r.ok) {{
      msg.style.color = '#178a56'; msg.textContent = '구독 완료! 감사합니다 \U0001F64C';
      document.getElementById('newsletterEmail').value = '';
    }} else {{
      const d = await r.json().catch(() => ({{}}));
      msg.style.color = '#c8333a'; msg.textContent = d.detail || '구독 처리 중 문제가 발생했어요.';
    }}
  }} catch (err) {{
    msg.style.color = '#c8333a'; msg.textContent = '네트워크 오류, 잠시 후 다시 시도해주세요.';
  }}
}});
</script>
<!--/newsletter-block-->
<footer>본 콘텐츠는 공개 데이터를 정량 분석한 <b>정보 제공·교육용</b>이며 특정 종목의 매수·매도
권유가 아닙니다. 데이터는 오류·지연이 있을 수 있고, 과거 성과는 미래를 보장하지 않습니다.
투자 판단과 책임은 이용자 본인에게 있습니다. · <a href="/about#privacy">개인정보처리방침</a>
· <a href="/about#disclaimer">면책조항</a></footer>""" if show_subscribe else ""
    return f"""<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-0C72PQQH21"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-0C72PQQH21');
</script>
<meta name="google-site-verification" content="5TVrZ_HlWRfb6pGJ1o-2YwzL1qnPxqpTwJSLWVGLM74" />
<meta name="google-adsense-account" content="ca-pub-2115777789192453">
<meta name="naver-site-verification" content="2f945cfe349bbdceb4341472d7d2a1cc69b26a1f" />
<meta name="naver-site-verification" content="8d698cb6521592ccddbba542f4cfdbe0f8d4a1fd" />
<link rel="icon" type="image/png" sizes="32x32" href="{parts.scheme}://{parts.netloc}/static/favicon-32.png">
<link rel="icon" type="image/png" sizes="16x16" href="{parts.scheme}://{parts.netloc}/static/favicon-16.png">
<link rel="apple-touch-icon" href="{parts.scheme}://{parts.netloc}/static/apple-touch-icon.png">
<title>머니체크업 · {_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{_esc(canonical)}">
<meta property="og:type" content="article"><meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}"><meta property="og:locale" content="ko_KR">
<meta property="og:url" content="{_esc(canonical)}">
<meta property="og:image" content="{_esc(og_image)}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{_esc(og_image)}">
<script type="application/ld+json">{_breadcrumb_ld(title, canonical)}</script>
<link rel="stylesheet" as="style" crossorigin
  href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css">
<style>
body{{max-width:900px;margin:0 auto;padding:20px 18px 60px;line-height:1.7;font-size:14.5px;
 font-family:'Pretendard Variable',Pretendard,-apple-system,"Segoe UI",Roboto,
 "Apple SD Gothic Neo","Malgun Gothic",sans-serif;color:#12161c;background:#fff}}
@media (prefers-color-scheme:dark){{body{{background:#0f1216;color:#f1f4f8}}a{{color:#5a9bdb}}
 th{{color:#aab6c2}} tr:hover{{background:#171c23}} .muted{{color:#aab6c2}}}}
a{{color:#1a63cf;text-decoration:none;font-weight:600}}a:hover{{text-decoration:underline}}
.top{{font-size:13px;color:#5a6472;margin-bottom:14px}}
h1{{font-size:20px}}h2{{font-size:16.5px;margin-top:26px}}
.ic{{width:14px;height:14px;vertical-align:-2px;margin-right:1px;flex:none;display:inline-block}}
h1 .ic{{width:17px;height:17px;vertical-align:-3px;margin-right:3px}}
h2 .ic{{width:15px;height:15px;vertical-align:-2px;margin-right:2px}}
table{{border-collapse:collapse;width:100%;font-size:13.5px;margin:10px 0}}
th,td{{padding:8px 10px;border-bottom:1px solid #8883;text-align:right;white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}
.wrap{{overflow-x:auto}} .muted{{color:#4a5563}} .pos{{color:#c8333a}} .neg{{color:#1f6fd1}}
.footnote{{font-size:12px}}
.warn{{background:rgba(242,85,90,.08);border:1px solid rgba(242,85,90,.3);padding:8px 14px;
  border-radius:7px;font-size:13.5px}}
.badge{{display:inline-block;padding:1px 8px;border-radius:10px;background:#8881;font-size:12.5px;margin:2px 3px 0 0}}
.dimgrid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:10px 0}}
@media(max-width:560px){{.dimgrid{{grid-template-columns:1fr}}}}
.dimcard{{border:1px solid #8883;border-radius:10px;padding:12px 14px;background:#8880.06}}
.dimhead{{font-weight:700;font-size:14.5px;display:flex;justify-content:space-between}}
.dimstars{{color:#e0a500;letter-spacing:1px;font-size:13px}}
.dimlabel{{font-size:12.5px;color:#4a5563;margin:2px 0 4px}}
.dimtext{{font-size:13.5px;margin:0;line-height:1.6}}
footer{{margin-top:32px;padding-top:16px;border-top:1px solid #8883;font-size:11.5px;color:#5a6472}}
</style></head><body>
<div class="top"><a href="/">← 대시보드로</a></div>
{body}
{subscribe_html}
</body></html>"""


def _stock_rows(stocks):
    out = ""
    for s in stocks:
        link = f'/s/{s["code"]}'
        if s.get("in_rank"):
            out += (f'<tr><td><a href="{link}">{_esc(s["name"])}</a> '
                    f'<span class="muted">{_esc(s["code"])}</span></td>'
                    f'<td><b>{_fmt(s.get("score"),1)}</b></td><td>{_fmt(s.get("per"))}</td>'
                    f'<td>{_fmt(s.get("pbr"),2)}</td><td>{_fmt(s.get("roe"))}</td>'
                    f'<td class="muted">{_esc(s.get("sector") or "")}</td></tr>')
        else:
            out += (f'<tr><td><a href="{link}">{_esc(s["name"])}</a> '
                    f'<span class="muted">{_esc(s["code"])}</span></td>'
                    f'<td class="muted">–</td><td class="muted">–</td><td class="muted">–</td>'
                    f'<td class="muted">–</td><td class="muted"></td></tr>')
    return out


def _others_note(stocks):
    others = [s for s in stocks if not s.get("in_rank")]
    if not others:
        return ""
    names = ", ".join(f'<a href="/s/{s["code"]}">{_esc(s["name"])}</a>'
                      for s in others[:40])
    more = f" 외 {len(others)-40}개" if len(others) > 40 else ""
    return (f'<p class="muted" style="font-size:12px">데이터 미수집(시총 소형 등) '
            f'{len(others)}개: {names}{more}</p>')


def _spark(prices):
    if not prices or len(prices) < 2:
        return '<p class="muted">가격 데이터 없음</p>'
    xs = [p["close"] for p in prices]
    n = len(prices)
    mn, mx = min(xs), max(xs)
    W, H = 640, 170
    padL, padR, padT, padB = 56, 8, 10, 22   # y축 라벨·x축 라벨 공간
    plotW, plotH = W - padL - padR, H - padT - padB

    def px(i):
        return padL + i / (n - 1) * plotW

    def py(v):
        return padT + plotH - (v - mn) / ((mx - mn) or 1) * plotH

    pts = " ".join(f'{px(i):.1f},{py(p["close"]):.1f}' for i, p in enumerate(prices))
    first, last = xs[0], xs[-1]
    color = "#c8333a" if last >= first else "#1f6fd1"
    pct = (last / first - 1) * 100
    cls = "pos" if last >= first else "neg"

    # y축: 최저/중간/최고 3줄 그리드+라벨
    grid = ""
    for frac in (0.0, 0.5, 1.0):
        v = mn + (mx - mn) * frac
        y = py(v)
        grid += (f'<line x1="{padL}" y1="{y:.1f}" x2="{W-padR}" y2="{y:.1f}" '
                f'stroke="#8883" stroke-width="1"/>'
                f'<text x="{padL-6}" y="{y+3:.1f}" font-size="10" fill="#8a95a1" '
                f'text-anchor="end">{v:,.0f}</text>')
    # x축: 4개 지점 날짜 라벨(YY.MM)
    xlabels = ""
    for frac in (0.0, 1 / 3, 2 / 3, 1.0):
        idx = min(n - 1, round(frac * (n - 1)))
        d = prices[idx]["date"]
        lbl = f"{d[2:4]}.{d[5:7]}" if len(d) >= 7 else d
        xlabels += (f'<text x="{px(idx):.1f}" y="{H-4}" font-size="10" fill="#8a95a1" '
                   f'text-anchor="middle">{lbl}</text>')

    return (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:170px">'
            f'{grid}<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/>'
            f'{xlabels}</svg>'
            f'<p class="muted">{prices[0]["date"]} {first:,.0f} → {prices[-1]["date"]} '
            f'{last:,.0f} (<span class="{cls}">{pct:+.1f}%</span>)</p>')


_PERIOD_LABELS = [("wow", "1주"), ("mom", "1개월"), ("qoq", "3개월"), ("yoy", "1년")]


def _period_pills_html(pr):
    if not pr:
        return ""
    cells = ""
    for key, label in _PERIOD_LABELS:
        v = pr.get(key)
        cls = "pos" if (v or 0) >= 0 else "neg"
        cells += (f'<div style="text-align:center;flex:1"><div class="muted" '
                  f'style="font-size:11px">{label}</div>'
                  f'<div class="{cls}" style="font-weight:700">'
                  f'{"–" if v is None else f"{v:+.1f}%"}</div></div>')
    return (f'<div style="display:flex;gap:4px;margin:6px 0 2px;padding:10px 4px;'
            f'border:1px solid #8883;border-radius:8px">{cells}</div>')


_DIM_META = {"value": ("wallet", "밸류에이션"), "profit": ("trendUp", "수익성"),
             "safety": ("shield", "안정성"), "growth": ("sprout", "성장성")}


def _stars_html(n):
    if n is None:
        return '<span class="muted">–</span>'
    return "★" * n + '<span class="muted">' + "☆" * (5 - n) + "</span>"


def _dims_html(dims):
    if not dims:
        return ""
    cards = ""
    for key, (icon_name, label) in _DIM_META.items():
        d = dims.get(key) or {}
        cards += (f'<div class="dimcard"><div class="dimhead">{_ic(icon_name)} {label} '
                  f'<span class="dimstars">{_stars_html(d.get("stars"))}</span></div>'
                  f'<div class="dimlabel">{_esc(d.get("label"))}</div>'
                  f'<p class="dimtext">{_esc(d.get("text"))}</p></div>')
    overall = dims.get("overall_text") or ""
    return (f'<h2>기업 건강검진 <span class="muted" style="font-size:13px;font-weight:400">'
            f'· 같은 업종·시총 내 상대 평가, 최근 연간 재무제표 기준</span></h2>'
            f'<div class="dimgrid">{cards}</div>'
            + (f'<p class="muted">{_esc(overall)}</p>' if overall else ""))


def _sev_dot(emoji):
    color = "#e0453f" if emoji == "\U0001F534" else "#e0a500"
    return (f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
            f'background:{color};margin-right:5px;vertical-align:1px"></span>')


def _flags_html(flags):
    if flags is None:
        return ""
    if not flags:
        return (f'<h2>{_ic("alert")} 참고할 점</h2><p class="muted">규칙 기반으로 확인한 특별한 '
                '재무 이상신호는 없습니다. (회계부정 진단이 아닌 참고 신호입니다)</p>')
    items = "".join(f'<p style="margin:6px 0">{_sev_dot(f["emoji"])}<b>{_esc(f["label"])}</b> — '
                    f'{_esc(f["text"])}</p>' for f in flags)
    return (f'<h2>{_ic("alert")} 참고할 점 <span class="muted" style="font-size:13px;font-weight:400">'
            f'· 규칙 기반 참고 신호, 회계부정 진단 아님</span></h2>{items}')


def _disclosures_html(items):
    if not items:
        return f'<h2>{_ic("document")} 공시자료</h2><p class="muted">최근 공시 데이터를 불러올 수 없습니다.</p>'
    rows = "".join(
        f'<p style="margin:6px 0"><a href="{_esc(d["link"])}" target="_blank" '
        f'rel="noopener">{_esc(d["title"])}</a> '
        f'<span class="muted" style="font-size:12px">{_esc(d.get("date"))} · '
        f'{_esc(d.get("submitter"))}</span></p>' for d in items)
    return (f'<h2>{_ic("document")} 공시자료 <span class="muted" style="font-size:13px;font-weight:400">'
            f'· DART 전자공시 원문</span></h2>{rows}')


def _audit_html(audit):
    if not audit or not audit.get("opinion"):
        return ""
    clean = "적정" in audit["opinion"]
    cls = "pos" if clean else "neg"
    warn = "" if clean else " ⚠️ 감사인이 재무제표에 문제를 제기한 상태입니다. 원문 공시를 꼭 확인하세요."
    yr = f'{audit["year"]}년 ' if audit.get("year") else ""
    auditor = f' ({_esc(audit["auditor"])})' if audit.get("auditor") else ""
    return (f'<p>회계감사인 감사의견 <span class="{cls}" style="font-weight:700">'
            f'{yr}{_esc(audit["opinion"])}{auditor}</span>{warn}</p>')


def _quarterly_rows_html(quarterly):
    if not quarterly:
        return ""
    def eok(v):
        return "–" if v is None else f"{round(v/1e8):,}"
    rows = "".join(
        f'<tr><td>{q["year"]} Q{q["quarter"]}</td><td>{eok(q.get("revenue"))}</td>'
        f'<td>{eok(q.get("op_profit"))}</td><td>{eok(q.get("net_income"))}</td>'
        f'<td>{_fmt(q.get("op_margin"))}</td><td>{_fmt(q.get("debt_ratio"),0)}</td></tr>'
        for q in quarterly)
    return (f'<h2>분기별 재무 <span class="muted" style="font-size:13px;font-weight:400">'
            f'· DART 분기·반기보고서 기준 단독분기 환산, 단위 억</span></h2>'
            f'<div class="wrap"><table><thead><tr><th>분기</th><th>매출</th><th>영업이익</th>'
            f'<th>순이익</th><th>영익률%</th><th>부채%</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


def render_stock_page(code, name, summary, financials, prices, news, themes,
                      disclosures, period_returns, canonical, audit=None, quarterly=None):
    def eok(v):
        return "–" if v is None else f"{round(v/1e8):,}"
    head = f'<h1>{_ic("barchart")} {_esc(name)} <span class="muted" style="font-size:15px">{_esc(code)}</span></h1>'
    head += '<p class="muted">재무제표·건강검진 점수·밸류에이션과 관련 뉴스를 한 페이지에서.</p>'
    head += _audit_html(audit)
    kpi = ""
    dims_html = ""
    if summary:
        kpi = (f'<p>가치+퀄리티 종합점수 <b>{_fmt(summary.get("score"))}</b> '
               f'<span class="muted" style="font-size:12px">(최근 연간 재무제표 기준)</span> · '
               f'<a href="/learn/per">PER</a> {_fmt(summary.get("per"))} · '
               f'<a href="/learn/pbr">PBR</a> {_fmt(summary.get("pbr"),2)} · '
               f'<a href="/learn/psr">PSR</a> {_fmt(summary.get("psr"),2)} · '
               f'<a href="/learn/roe">ROE</a> {_fmt(summary.get("roe"))}% · '
               f'<a href="/learn/op-margin">영업이익률</a> {_fmt(summary.get("op_margin"))}% · '
               f'<a href="/learn/debt-ratio">부채비율</a> {_fmt(summary.get("debt_ratio"),0)}% · '
               f'<a href="/learn/dividend-yield">배당수익률</a> {_fmt(summary.get("div_yield"),2)}% · '
               f'시총 {summary.get("marcap_eok",0):,}억</p>')
        dims_html = _dims_html(summary.get("dims"))
        flags_html = _flags_html(summary.get("flags"))
    else:
        flags_html = ""
    tbadge = ""
    if themes:
        tbadge = '<p>' + "".join(
            f'<a href="/t/{_esc(t["no"])}" style="text-decoration:none">'
            f'<span class="badge">{_esc(t["name"])}</span></a>' for t in themes[:12]
        ) + '</p>'
    fin_rows = "".join(
        f'<tr><td>{f["year"]}</td><td>{eok(f.get("revenue"))}</td>'
        f'<td>{eok(f.get("op_profit"))}</td><td>{eok(f.get("net_income"))}</td>'
        f'<td>{eok(f.get("equity"))}</td><td>{_fmt(f.get("op_margin"))}</td>'
        f'<td>{_fmt(f.get("debt_ratio"),0)}</td></tr>' for f in financials)
    news_html = "".join(
        f'<p style="margin:8px 0"><a href="{_esc(n["link"])}" target="_blank" '
        f'rel="noopener">{_esc(n["title"])}</a><br>'
        f'<span class="muted" style="font-size:12px">{_esc(n.get("source"))} · '
        f'{_esc(n.get("pub"))}</span></p>' for n in news) or '<p class="muted">뉴스 없음</p>'
    disc_html = _disclosures_html(disclosures)
    body = f"""{head}{kpi}{tbadge}
{dims_html}
{flags_html}
<h2>주가 (최근)</h2>{_spark(prices)}{_period_pills_html(period_returns)}
<h2>재무 추이 (DART 사업보고서, 단위 억)</h2>
<div class="wrap"><table><thead><tr><th>연도</th><th>매출</th><th>영업이익</th>
<th>순이익</th><th>자본</th><th>영익률%</th><th>부채%</th></tr></thead>
<tbody>{fin_rows or '<tr><td colspan=7 class="muted">재무 데이터 없음</td></tr>'}</tbody></table></div>
{_quarterly_rows_html(quarterly)}
{disc_html}
<h2>관련 뉴스 <span class="muted" style="font-size:13px;font-weight:400">· 구글뉴스</span></h2>
{news_html}
<p class="muted" style="margin-top:16px"><a href="/">← 대시보드에서 전체 종목 보기</a></p>"""
    desc = f"{name}({code}) 재무제표(매출·영업이익·ROE·부채비율), 밸류에이션, 관련 뉴스."
    return layout(f"{name} ({code}) 재무·밸류에이션·뉴스 | 한국주식", desc, canonical, body)


def render_theme_page(name, stocks, perf, canonical):
    ranked = [s for s in stocks if s.get("in_rank")]
    n_total, n_ranked = len(stocks), len(ranked)
    r1 = perf.get("ret_1m") if perf else None
    r3 = perf.get("ret_3m") if perf else None
    # 원본 코멘트 자동 생성
    top = sorted(ranked, key=lambda s: s.get("score") or 0, reverse=True)[:3]
    top_names = ", ".join(_esc(s["name"]) for s in top) if top else "해당 없음"
    cheap = sorted([s for s in ranked if s.get("per")],
                   key=lambda s: s["per"])[:3]
    cheap_names = ", ".join(f'{_esc(s["name"])}(PER {_fmt(s["per"])})' for s in cheap) \
        if cheap else "해당 없음"
    perf_txt = ""
    if r1 is not None:
        dir1 = "강세" if r1 > 0 else "약세"
        perf_txt = (f" 최근 1개월 이 테마 구성종목의 동일가중 수익률은 "
                    f"<b class='{'pos' if r1>=0 else 'neg'}'>{_fmt(r1)}%</b>({dir1}), "
                    f"3개월은 {_fmt(r3)}% 입니다.")

    body = f"""
<h1>{_ic('gem')} {_esc(name)} 관련주 — 가치·퀄리티 분석</h1>
<p class="muted">구성종목 {n_total}개 중 {n_ranked}개를 가치+퀄리티 팩터점수로 분석.
점수↑ = 저평가·우량 상대순위.{perf_txt}</p>
<p>{_esc(name)} 테마에서 <b>가치+퀄리티 종합 상위</b>는 {top_names} 입니다.
밸류에이션(PER) 기준 저평가 상위는 {cheap_names} 입니다. 아래 표는 팩터 종합점수 순
정렬이며, 지주사·금융주 등은 비율이 왜곡될 수 있어 참고로만 보시기 바랍니다.</p>
<div class="wrap"><table>
<thead><tr><th>종목</th><th>팩터점수</th><th>PER</th><th>PBR</th><th>ROE%</th><th>섹터</th></tr></thead>
<tbody>{_stock_rows(sorted(ranked, key=lambda s: s.get("score") or 0, reverse=True))}</tbody>
</table></div>
{_others_note(stocks)}
<p class="muted footnote">※ 팩터점수는 시총 3,000억 이상 유니버스 내 백분위 기준. 재무=DART 최신
사업보고서. 테마 분류는 공개 테마 데이터를 참고했으며, 종목 선별·정렬·분석은 본 사이트의
자체 팩터 모델에 의한 것입니다.</p>
"""
    desc = (f"{name} 관련주를 가치+퀄리티 팩터로 분석. 저평가·우량 상위 종목과 "
            f"PER·PBR·ROE, 최근 수익률까지 한눈에.")
    return layout(f"{name} 관련주 — 가치·퀄리티 분석 | 한국주식 팩터", desc, canonical, body)


_FLAG_EXPLAIN = {
    "비적정 감사의견": "회계감사인이 재무제표에 '적정' 의견을 주지 않은 경우입니다(한정·부적정·의견거절). "
                   "감사인이 재무 신뢰성 자체에 문제를 제기했다는 뜻으로, 상장폐지 사유가 될 수 있는 "
                   "가장 심각한 유형의 신호입니다. 반드시 원문 공시를 직접 확인하세요.",
    "적자 전환": "전년에는 순이익이 흑자였는데 올해는 적자로 바뀐 경우입니다. "
                "일시적 요인(자산매각 손실, 구조조정 등)인지 본업 악화인지 재무제표를 "
                "직접 확인해볼 필요가 있습니다.",
    "영업외 손익 의존": "본업(영업활동)에서는 손실이 났지만 자산매각·투자수익 등"
                     "영업외 요인 덕에 최종 순이익은 흑자로 나온 경우입니다. "
                     "본업 경쟁력과 별개로 순이익만 보면 실제보다 좋아 보일 수 있습니다.",
    "부채비율 급증": "1년 사이 부채비율이 50%포인트 이상 급격히 늘었습니다. 대규모 투자·차입,"
                  " 인수합병, 실적 악화로 인한 자본 감소 등 원인을 확인해볼 필요가 있습니다."
                  " 다만 증권·캐피탈 등 금융 계열사를 연결로 잡는 지주사는 원래 부채비율이"
                  " 매우 높게(수백~1000%대) 나오는 게 정상이라, 절대 수준이 이미 높았다면"
                  " 위험 신호보다는 그런 구조 때문일 가능성도 감안해서 보세요.",
    "매출 2년 연속 감소": "최근 2개 회계연도 모두 매출이 전년보다 줄었습니다. "
                      "업종 전반의 불황인지, 개별 기업의 경쟁력 약화인지 살펴볼 필요가 있습니다.",
    "분기 적자 전환": "가장 최근 분기가 전년 동기(계절성 회피) 대비 흑자에서 적자로 전환됐습니다. "
                   "연간 결산을 기다리지 않고 분기 단위로 더 빠르게 잡아낸 신호입니다.",
    "분기 영업외 손익 의존": "가장 최근 분기의 영업이익은 적자이나 순이익은 흑자입니다. "
                        "본업 외 요인(자산매각·평가이익 등)에 기댄 결과일 수 있습니다.",
    "분기 부채비율 급증": "직전 분기 대비 부채비율이 20%포인트 이상 늘었습니다. 짧은 기간(3개월) 내 "
                      "급격한 변화라 원인을 확인해볼 필요가 있습니다. 금융 계열사를 연결로 잡는"
                      " 지주사라면 원래 절대 수준이 높을 수 있습니다.",
    "매출 2분기 연속 감소": "최근 2개 분기 모두 매출이 전년 동기 대비 감소했습니다. "
                        "연간 수치에는 아직 안 드러났을 수 있는 조기 신호입니다.",
}


def render_anomaly_report(grouped, asof, canonical):
    """flags(이상신호)가 감지된 종목을 유형별로 모은 리포트."""
    total = sum(len(v) for v in grouped.values())
    labels = sorted(grouped.keys(), key=lambda label: (
        0 if grouped[label][0]["emoji"] == "\U0001F534" else 1, -len(grouped[label])))
    sections = ""
    for label in labels:
        items = sorted(grouped[label], key=lambda s: s.get("marcap_eok") or 0, reverse=True)
        rows = "".join(
            f'<tr><td style="text-align:left"><a href="/s/{_esc(s["code"])}">{_esc(s["name"])}</a> '
            f'<span class="muted">{_esc(s["code"])}</span></td>'
            f'<td style="text-align:left">{_esc(s["text"])}</td></tr>' for s in items)
        sections += (f'<h2>{items[0]["emoji"]} {_esc(label)} <span class="muted" '
                    f'style="font-size:13px;font-weight:400">· {len(items)}개 종목</span></h2>'
                    f'<p>{_esc(_FLAG_EXPLAIN.get(label, ""))}</p>'
                    f'<div class="wrap"><table style="table-layout:fixed;width:100%">'
                    f'<colgroup><col style="width:30%"><col style="width:70%"></colgroup>'
                    f'<thead><tr><th style="text-align:left">종목</th>'
                    f'<th style="text-align:left">내용</th></tr></thead>'
                    f'<tbody>{rows}</tbody></table></div>')
    if not sections:
        sections = '<p class="muted">현재 이상신호가 감지된 종목이 없습니다.</p>'
    body = f"""
<h1>{_ic('alert')} 이상신호 리포트 <span class="muted" style="font-size:14px">({_esc(asof)} 기준)</span></h1>
<p class="muted">시총 3,000억 이상 유니버스 기준, 규칙 기반으로 감지된 참고 신호 전체 {total}건.</p>
<p>재무 데이터에서 <b>규칙 기반으로 감지된 참고 신호</b>를 모았습니다. 적자 전환, 부채비율
급증, 영업외 손익 의존, 매출 2년 연속 감소 — 4가지 유형을 자동으로 스캔합니다.
<b>회계부정을 진단하는 도구가 아니며</b>, "한번 확인해볼 만한 종목"을 걸러주는 참고 신호입니다.
매수·매도 추천이 아닙니다. 심각도(적자전환 등) 높은 유형 순으로 정렬했으며, 신호가 뜬 종목은
클릭해서 실제 재무제표·공시 원문을 직접 확인해보세요.</p>
{sections}
<p class="muted footnote">데이터: DART 최신 사업보고서. 규칙 기반 참고 신호이며 회계부정 진단이 아닙니다.</p>
"""
    desc = f"{asof} 기준 적자전환·부채비율급증·영업외손익의존·매출감소 등 재무 이상신호가 감지된 한국 상장기업 리포트."
    return layout(f"이상신호 리포트 ({asof}) — 적자전환·부채급증 감지 기업",
                  desc, canonical, body, show_subscribe=False)


def _movers_rows(movers):
    if not movers:
        return '<tr><td colspan="4" class="muted">데이터 부족</td></tr>'
    rows = []
    for m in movers:
        cls = "pos" if m["rank_change"] > 0 else "neg"
        arrow = "▲" if m["rank_change"] > 0 else "▼"
        sc_cls = "pos" if m["score_change"] >= 0 else "neg"
        rows.append(f'<tr><td style="text-align:left"><a href="/s/{_esc(m["code"])}">{_esc(m["name"])}</a></td>'
                    f'<td>{m["rank"]}위</td><td class="{cls}">{arrow}{abs(m["rank_change"])}</td>'
                    f'<td class="{sc_cls}">{m["score_change"]:+.1f}</td></tr>')
    return "".join(rows)


def _movers_section(movers_up, movers_down, period_label):
    if not movers_up and not movers_down:
        return ""
    return f"""
<h2>{_ic('barchart')} 종합점수 순위 변동 ({period_label} 대비)</h2>
<p class="muted">{period_label} 전 가격을 기준으로 다시 계산한 점수와 비교했습니다(재무제표는 최신 값을 그대로 사용).
가격이 올라 밸류에이션 매력이 줄면 순위가 내려가고, 내려서 저평가 매력이 커지면 순위가 오릅니다.</p>
<h3>{_ic('trendUp')} 순위 상승 TOP{len(movers_up)}</h3>
<div class="wrap"><table><thead><tr><th style="text-align:left">종목</th><th>현재순위</th>
<th>변동</th><th>점수변동</th></tr></thead><tbody>{_movers_rows(movers_up)}</tbody></table></div>
<h3>{_ic('trendDown')} 순위 하락 TOP{len(movers_down)}</h3>
<div class="wrap"><table><thead><tr><th style="text-align:left">종목</th><th>현재순위</th>
<th>변동</th><th>점수변동</th></tr></thead><tbody>{_movers_rows(movers_down)}</tbody></table></div>
"""


_DIM_LABELS = [("value", "wallet", "밸류에이션", "per", "PER", "배", True),
              ("profit", "trendUp", "수익성", "roe", "ROE", "%", False),
              ("safety", "shield", "안정성", "debt_ratio", "부채비율", "%", True),
              ("growth", "sprout", "성장성", "rev_growth", "매출성장률", "%", False)]


def _dim_leader_table(rows, dim_key, metric_key, metric_label, unit, lower_better):
    scored = [r for r in rows if r.get("dims", {}).get(dim_key, {}).get("stars") is not None]
    scored.sort(key=lambda r: (r["dims"][dim_key]["stars"],
                                -(r.get(metric_key) or 0) if lower_better else (r.get(metric_key) or 0)),
                reverse=True)
    top = scored[:5]
    nd = 2 if unit == "배" else 1
    trs = "".join(
        f'<tr><td style="text-align:left"><a href="/s/{_esc(r["code"])}">{_esc(r["name"])}</a></td>'
        f'<td>{"★"*r["dims"][dim_key]["stars"]}</td>'
        f'<td>{_fmt(r.get(metric_key), nd)}{unit}</td></tr>' for r in top)
    return trs or '<tr><td colspan=3 class="muted">데이터 부족</td></tr>'


def render_monthly_health(rows, anomaly_count, asof, canonical, movers_up=None, movers_down=None):
    """이번 달 건강점수 랭킹 — 종합점수 TOP20 + 4차원별 최고 TOP5."""
    top20 = sorted(rows, key=lambda r: r.get("score") or 0, reverse=True)[:20]
    top_rows = "".join(
        f'<tr><td style="text-align:left"><a href="/s/{_esc(r["code"])}">{_esc(r["name"])}</a> '
        f'<span class="muted">{_esc(r["code"])}</span></td><td><b>{_fmt(r.get("score"))}</b></td>'
        f'<td>{_fmt(r.get("per"))}</td><td>{_fmt(r.get("pbr"),2)}</td>'
        f'<td>{_fmt(r.get("roe"))}</td></tr>' for r in top20)
    dim_sections = ""
    for key, icon_name, label, metric_key, metric_label, unit, lower_better in _DIM_LABELS:
        dim_sections += (f'<h3>{_ic(icon_name)} {label} 최고 TOP5</h3>'
                         f'<div class="wrap"><table><thead><tr><th style="text-align:left">종목</th>'
                         f'<th>별점</th><th>{metric_label}</th></tr></thead>'
                         f'<tbody>{_dim_leader_table(rows, key, metric_key, metric_label, unit, lower_better)}'
                         f'</tbody></table></div>')
    body = f"""
<h1>{_ic('target')} 이번 달 건강점수 랭킹 <span class="muted" style="font-size:14px">({_esc(asof)} 기준)</span></h1>
<p class="muted">시총 3,000억 이상 유니버스 기준, 가치+퀄리티 종합점수 TOP20과 4차원 건강검진 별점 랭킹입니다.</p>
<p>밸류에이션·수익성·안정성·성장성 4차원 건강검진 별점을 기준으로 이번 달 상위 기업을 정리했습니다.
매수·매도 추천이 아니라 <b>같은 유니버스 내 상대 비교</b> 스냅샷입니다.</p>

<div class="warn" style="margin:12px 0">{_ic('alert')} 이번 달 재무 이상신호(적자전환·부채급증 등)가
감지된 종목은 <b>{anomaly_count}개</b>입니다. <a href="/anomaly-report">→ 이상신호 리포트 먼저 보기</a></div>

<h2>{_ic('trophy')} 종합점수 TOP20</h2>
<div class="wrap"><table><thead><tr><th style="text-align:left">종목</th><th>점수</th>
<th>PER</th><th>PBR</th><th>ROE%</th></tr></thead><tbody>{top_rows}</tbody></table></div>

<h2>차원별 최고 기업</h2>
<p class="muted footnote">같은 별점 안에서도 실제 수치는 다를 수 있어 지표 값을 함께 표시했습니다.</p>
{dim_sections}
{_movers_section(movers_up, movers_down, "한 달")}
<p class="muted footnote">데이터: FinanceDataReader·DART. 분석·정렬은 자체 팩터 모델. 매매 추천이 아닙니다.</p>
"""
    desc = f"{asof} 기준 가치+퀄리티 건강점수 TOP20과 밸류에이션·수익성·안정성·성장성 4차원 최고 기업 랭킹."
    return layout(f"이번 달 건강점수 랭킹 ({asof}) — 종합점수 TOP20 + 4차원 우수기업",
                  desc, canonical, body, show_subscribe=False)


def render_weekly(strong, weak, asof, canonical, movers_up=None, movers_down=None):
    def theme_li(t):
        cls = "pos" if (t["ret_1m"] or 0) >= 0 else "neg"
        return (f'<tr><td><a href="/t/{t["no"]}">{_esc(t["name"])}</a></td>'
                f'<td class="{cls}">{_fmt(t["ret_1m"])}</td>'
                f'<td>{_fmt(t["ret_3m"])}</td><td class="muted">{t["priced"]}/{t["count"]}</td></tr>')
    strong_rows = "".join(theme_li(t) for t in strong)
    weak_rows = "".join(theme_li(t) for t in weak)
    top_theme = strong[0]["name"] if strong else "–"

    body = f"""
<h1>{_ic('news')} 주간 한국주식 시장 리포트 <span class="muted" style="font-size:14px">({_esc(asof)} 기준)</span></h1>
<p class="muted">시총 3,000억 이상 유니버스 기준, 최근 1개월 테마 동일가중 수익률 강세·약세 순위입니다.</p>
<p>최근 1개월 기준 가장 강했던 테마는 <b>{_esc(top_theme)}</b> 입니다. 아래는 테마별
구성종목 동일가중 수익률로 본 강세·약세 순위입니다. 가치+퀄리티 팩터 종합순위는
<a href="/monthly">월간 건강랭킹</a>에서 확인하세요. 매매 추천이 아니라 데이터로 본
흐름 정리입니다.</p>

<h2>{_ic('flame')} 강세 테마 TOP 10 (최근 1개월)</h2>
<div class="wrap"><table><thead><tr><th>테마</th><th>1개월%</th><th>3개월%</th><th>종목수</th></tr></thead>
<tbody>{strong_rows}</tbody></table></div>

<h2>{_ic('trendDown')} 약세 테마 (최근 1개월)</h2>
<div class="wrap"><table><thead><tr><th>테마</th><th>1개월%</th><th>3개월%</th><th>종목수</th></tr></thead>
<tbody>{weak_rows}</tbody></table></div>
{_movers_section(movers_up, movers_down, "일주일")}
<p class="muted footnote">데이터: FinanceDataReader·DART·공개 테마/뉴스 피드. 분석·정렬은 자체 팩터 모델.</p>
"""
    desc = f"{asof} 기준 한국주식 주간 리포트 — 최근 1개월 강세/약세 테마와 종합점수 순위 변동 정리."
    return layout(f"주간 한국주식 시장 리포트 ({asof}) — 강세 테마·순위 변동",
                  desc, canonical, body, show_subscribe=False)


def render_earnings_report(items, canonical):
    """최근 공시된 분기 실적 발표 현황 — '예정' 캘린더가 아니라 이미 나온 것 중 최신순."""
    def growth_cell(yoy, qoq):
        # 전년 동기 데이터가 없으면(수집 기간이 2개년뿐이라 초반 분기는 흔함) 직전 분기
        # 대비(QoQ)로 대체 표시 — 계산 안 된 게 아니라 비교 기준 데이터가 없는 것뿐이라,
        # "–"만 찍기보다 QoQ라도 보여주는 게 낫다는 판단.
        v, label = (yoy, "") if yoy is not None else (qoq, ' <small class="muted">(QoQ)</small>')
        if v is None:
            return "–"
        cls = "pos" if v >= 0 else "neg"
        return f'<span class="{cls}">{v:+.1f}%</span>{label}'

    rows = "".join(
        f'<tr><td style="text-align:left"><a href="/s/{_esc(it["code"])}">{_esc(it["name"])}</a></td>'
        f'<td>{it["year"]} Q{it["quarter"]}</td><td>{_esc(it["disclosed_date"])}</td>'
        f'<td>{growth_cell(it["rev_yoy"], it.get("rev_qoq"))}</td>'
        f'<td>{growth_cell(it["ni_yoy"], it.get("ni_qoq"))}</td></tr>'
        for it in items) or '<tr><td colspan=5 class="muted">데이터 없음</td></tr>'
    rev_yoys = [it["rev_yoy"] for it in items if it.get("rev_yoy") is not None]
    ni_yoys = [it["ni_yoy"] for it in items if it.get("ni_yoy") is not None]
    avg_note = ""
    if rev_yoys or ni_yoys:
        rev_avg = f"{sum(rev_yoys)/len(rev_yoys):+.1f}%" if rev_yoys else "–"
        ni_avg = f"{sum(ni_yoys)/len(ni_yoys):+.1f}%" if ni_yoys else "–"
        avg_note = (f'<p class="muted">이 목록 평균: 매출 YoY <b>{rev_avg}</b> · '
                    f'순이익 YoY <b>{ni_avg}</b> — 개별 종목 성장률과 비교해보세요.</p>')
    body = f"""
<h1>{_ic('calendar')} 최근 실적발표 현황</h1>
<p class="muted">DART 최근 공시 기준, 분기·반기 실적을 발표일 순으로 정리한 목록입니다.</p>
<p>전년 동기 대비 매출·순이익 성장률로 실적 흐름을 빠르게 훑어볼 수 있습니다(전년 동기 데이터가
없는 분기는 직전 분기 대비 <b>QoQ</b>로 대체 표시). <b>"다음 주 발표 예정"같은
사전 예측이 아니라 이미 공시된 실적만</b> 다룹니다 — DART는 공시 일정을 미리 알려주지
않아 정확한 예정일을 제공할 수 없기 때문입니다.</p>
{avg_note}
<div class="wrap"><table><thead><tr><th style="text-align:left">종목</th><th>분기</th>
<th>발표일</th><th>매출 YoY</th><th>순이익 YoY</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="muted footnote">데이터: DART 분기·반기보고서(단독분기 환산). 매매 추천이 아닙니다.</p>
"""
    desc = "최근 공시된 한국 상장기업 분기 실적 발표 현황과 전년 동기 대비 매출·순이익 성장률 정리."
    return layout("최근 실적발표 현황 — 분기 실적 발표일·전년동기 성장률",
                  desc, canonical, body, show_subscribe=False)


# ── 데일리/주간 인사이트 아티클 ────────────────────────────────────────────
# daily_content.py가 매일 content_out/{날짜}/blog_draft.txt로 커밋해두는 편집 글을
# 사이트에 크롤링 가능한 아티클로 노출. 리포트 섹션(실시간 데이터 뷰)과 달리, 날짜별
# 영구 URL로 매일 하나씩 '쌓이는' 원본 편집 콘텐츠 아카이브 — 애드센스가 요구하는
# '고유하고 지속적으로 늘어나는 콘텐츠'의 핵심. blog_draft.txt는 제목 한 줄 + '===='
# 밑줄 + 본문(이모지 섹션 헤더 + 불릿) 구조라, 이를 아티클 HTML로 변환한다.

# 본문 줄의 맨 앞이 이모지면 섹션 헤더(h2)로 간주. 👉(CTA)는 헤더가 아니라 문단.
def _lead_is_emoji(line):
    s = line.lstrip()
    if not s:
        return False
    cp = ord(s[0])
    return cp >= 0x1F000 or (0x2600 <= cp <= 0x27BF) or (0x2190 <= cp <= 0x21FF)


def _insight_body_html(body_text):
    """blog_draft.txt 본문(제목/밑줄 제거한 나머지)을 아티클 HTML로 변환.
    - 이모지로 시작하는 줄 → <h2> (단 👉 CTA 줄은 문단)
    - '- ' 불릿 → <li>, '  - ' 들여쓴 불릿 → 중첩 <li>
    - '#해시태그' 줄 → 태그 배지, '※' 줄 → 각주
    - 빈 줄 → 문단 구분, 그 외 → <p>"""
    lines = body_text.split("\n")
    out = []
    list_open = 0  # 현재 열린 <ul> 깊이(0/1/2)

    def close_lists(to=0):
        nonlocal list_open
        while list_open > to:
            out.append("</ul>")
            list_open -= 1

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            close_lists(0)
            continue
        # 불릿(중첩 여부는 선행 공백으로 판단)
        indent = len(line) - len(line.lstrip())
        if stripped.startswith("- "):
            depth = 2 if indent >= 2 else 1
            while list_open < depth:
                out.append("<ul>")
                list_open += 1
            close_lists(depth)
            out.append(f"<li>{_esc(stripped[2:])}</li>")
            continue
        close_lists(0)
        if stripped.startswith("#"):
            tags = "".join(f'<span class="badge">{_esc(t)}</span>'
                           for t in stripped.split() if t.startswith("#"))
            out.append(f'<p class="tagrow">{tags}</p>')
        elif stripped.startswith("※"):
            out.append(f'<p class="footnote muted">{_esc(stripped)}</p>')
        elif _lead_is_emoji(stripped) and not stripped.startswith("\U0001F449"):
            out.append(f"<h2>{_esc(stripped)}</h2>")
        else:
            out.append(f"<p>{_esc(stripped)}</p>")
    close_lists(0)
    return "\n".join(out)


def _insight_date_kr(date_str):
    y, m, d = date_str.split("-")
    return f"{int(y)}년 {int(m)}월 {int(d)}일"


def _strip_web_tail(body_text):
    """웹 아티클에서만 잘라내는 꼬리 블록. blog_draft.txt 끝의 CTA(👉)·"전 종목 스크리닝"
    안내·면책조항(※)·해시태그(#)는 네이버 블로그·인스타·뉴스레터엔 필요하지만, 사이트
    안에서는 (1) "머니체크업에서 확인하세요" CTA가 이미 사이트 안이라 어색하고 (2) 면책은
    layout() 푸터에 이미 있어 중복이며 (3) 해시태그 벽은 애드센스에 키워드 스터핑 신호로
    감점이라 웹에서만 제거한다. 원본 파일은 그대로 두므로 다른 채널엔 영향 없음."""
    lines = body_text.split("\n")
    cut = len(lines)
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith(("\U0001F449", "※", "#")):  # 👉 CTA / 면책 / 해시태그
            cut = i
            break
    kept = lines[:cut]
    while kept and not kept[-1].strip():   # 잘라낸 뒤 남은 끝 빈 줄 제거
        kept.pop()
    return "\n".join(kept)


def render_insight(date_str, title, body_text, prev_key, next_key, canonical):
    """개별 인사이트 아티클 페이지. prev_key/next_key: 인접 날짜(YYYY-MM-DD) 또는 None."""
    body_text = _strip_web_tail(body_text)
    body_html = _insight_body_html(body_text)
    nav = []
    if prev_key:
        nav.append(f'<a href="/insights/{prev_key}">← {_insight_date_kr(prev_key)}</a>')
    nav.append('<a href="/insights">전체 목록</a>')
    if next_key:
        nav.append(f'<a href="/insights/{next_key}">{_insight_date_kr(next_key)} →</a>')
    nav_html = ' · '.join(nav)
    pager = (f'<nav class="ins-pager" style="display:flex;gap:14px;flex-wrap:wrap;'
             f'font-size:13.5px">{nav_html}</nav>')
    body = f"""
<article>
<h1>{_esc(title)}</h1>
<p class="muted" style="margin:-4px 0 12px">{_ic('calendar')} {_insight_date_kr(date_str)} 발행 · 머니체크업 데일리 브리핑</p>
{pager}
{body_html}
</article>
<div style="margin-top:26px">{pager}</div>
"""
    # desc: 본문 첫 산문 문단에서 요약 추출(이모지 헤더·불릿·빈 줄 제외)
    snippet = ""
    for ln in body_text.split("\n"):
        s = ln.strip()
        if s and not _lead_is_emoji(s) and not s.startswith(("-", "#", "※", "(")):
            snippet = s
            break
    desc = (snippet or title)[:150]
    return layout(title, desc, canonical, body)


def render_insights_index(entries, canonical):
    """인사이트 아카이브 목록. entries: [{date, title, snippet}] 최신순."""
    cards = []
    for e in entries:
        cards.append(
            f'<a href="/insights/{e["date"]}" class="insight-card">'
            f'<div class="ic-date">{_ic("calendar")} {_insight_date_kr(e["date"])}</div>'
            f'<div class="ic-title">{_esc(e["title"])}</div>'
            f'<div class="ic-snip muted">{_esc(e["snippet"])}</div></a>')
    cards_html = "\n".join(cards) or '<p class="muted">아직 발행된 글이 없습니다.</p>'
    body = f"""
<h1>{_ic('news')} 데일리 마켓 브리핑</h1>
<p>매일 아침(주말엔 주간 마무리) 코스피·코스닥의 급등락·실적 발표·재무 이상신호·주도테마를
사람이 읽기 좋게 정리한 원본 브리핑입니다. 각 글은 그날의 공개 데이터를 자체 팩터 모델로
해석한 것으로, 매매 추천이 아니라 시장 흐름을 빠르게 훑기 위한 정보·교육용 콘텐츠입니다.</p>
<style>
.insight-card{{display:block;border:1px solid #8883;border-radius:10px;padding:14px 16px;
 margin:10px 0;text-decoration:none;color:inherit;font-weight:400}}
.insight-card:hover{{border-color:#1a63cf;text-decoration:none}}
.insight-card .ic-date{{font-size:12.5px;color:#5a6472}}
.insight-card .ic-title{{font-weight:700;font-size:15.5px;margin:3px 0}}
.insight-card .ic-snip{{font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.tagrow .badge{{font-size:12px}}
</style>
{cards_html}
"""
    desc = "코스피·코스닥 급등락·실적발표·이상신호·주도테마를 매일 정리한 데일리 마켓 브리핑 아카이브 — 머니체크업."
    return layout("데일리 마켓 브리핑 — 코스피·코스닥 매일 시장 정리", desc, canonical, body)
