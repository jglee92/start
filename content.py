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


def _josa_ga(name):
    """이름 마지막 글자 받침 유무로 '이'/'가' 조사를 고른다(한글 유니코드 완성형은
    (초성*21+중성)*28+종성+0xAC00으로 인코딩돼, %28==0이면 받침 없음).
    영문/숫자로 끝나는 종목명(예: LG, SK)은 받침 없는 것으로 간주해 '가'를 쓴다."""
    if not name:
        return "가"
    ch = name[-1]
    code = ord(ch) - 0xAC00
    if 0 <= code <= 11171:
        return "가" if code % 28 == 0 else "이"
    return "가"


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


def layout(title, desc, canonical, body, show_subscribe=True, noindex=False, extra_head=""):
    """noindex=True: 검색엔진 색인만 막고(noindex) 내부 링크는 계속 따라가게(follow) 한다
    — 사용자·SPA 기능엔 영향 없이, 애드센스 심사 관점에서 부가가치가 낮은 자동생성
    페이지(예: /t/{테마})만 색인 대상에서 빼기 위한 용도(sitemap.xml 제외와 항상 짝지어 씀).
    extra_head: 페이지별 추가 JSON-LD 등을 <head>에 끼워넣는 용도(예: 인사이트 아티클의
    Article 스키마 — 전체 페이지에 다 필요한 게 아니라 layout() 공통 인자로는 안 두고
    호출부에서 선택적으로 넘긴다)."""
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
    robots_tag = '<meta name="robots" content="noindex,follow">\n' if noindex else ""
    return f"""<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{robots_tag}<script async src="https://www.googletagmanager.com/gtag/js?id=G-0C72PQQH21"></script>
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
{extra_head}<link rel="preload" as="style" crossorigin
  href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css"
  onload="this.onload=null;this.rel='stylesheet'">
<noscript><link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css"></noscript>
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
.cat-details{{border:1px solid #8883;border-radius:10px;margin:14px 0;overflow:hidden}}
.cat-details>summary{{display:flex;align-items:center;gap:6px;padding:11px 14px;cursor:pointer;
  list-style:none;background:#8881}}
.cat-details>summary::-webkit-details-marker{{display:none}}
.cat-details>summary:before{{content:"▸";color:#4a5563;flex:none}}
.cat-details[open]>summary:before{{content:"▾"}}
.cat-details>.cat-body{{padding:12px 14px 14px}}
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
            out += (f'<tr><td><a href="{link}">{_esc(s["name"])}</a>{_smallcap_mark(s)} '
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
    return (f'<p class="muted" style="font-size:12px">재무 데이터 미수집·적자 등으로 '
            f'점수 미산출 {len(others)}개: {names}{more}</p>')


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


def _smallcap_mark(r):
    """시총 300억 미만(백테스트 미검증 초소형주) 종목 옆에 붙는 '[참고]' 마커.
    300억~3,000억 구간은 2026-07 별도 백테스트로 검증돼 배지 대상에서 빠졌다."""
    if not r.get("small_cap"):
        return ""
    return (' <span class="muted" style="font-size:11px" '
            'title="시총 300억 미만 · 백테스트 미검증 참고용">[참고]</span>')


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
                      disclosures, period_returns, canonical, audit=None, quarterly=None,
                      noindex=False):
    def eok(v):
        return "–" if v is None else f"{round(v/1e8):,}"
    head = f'<h1>{_ic("barchart")} {_esc(name)} <span class="muted" style="font-size:15px">{_esc(code)}</span></h1>'
    head += '<p class="muted">재무제표·건강검진 점수·밸류에이션과 관련 뉴스를 한 페이지에서.</p>'
    head += _audit_html(audit)
    kpi = ""
    dims_html = ""
    if summary:
        smallcap_badge = ""
        if summary.get("small_cap"):
            smallcap_badge = (' <span class="badge" style="background:#fff3cd;color:#8a6d00">'
                               '참고용 · 백테스트 미검증 초소형주(시총 300억 미만)</span>')
        kpi = (f'<p>가치+퀄리티 종합점수 <b>{_fmt(summary.get("score"))}</b>{smallcap_badge} '
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
    return layout(f"{name} ({code}) 재무·밸류에이션·뉴스 | 한국주식", desc, canonical, body,
                  noindex=noindex)


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
<p class="muted footnote">※ 팩터점수는 코스피·코스닥 전 종목 대상 백분위 기준이며, 시총 300억 미만 초소형주는
백테스트로 검증되지 않아 참고용으로만 표시됩니다(300억~3,000억 구간은 별도 백테스트로 검증됨).
재무=DART 최신
사업보고서. 테마 분류는 공개 테마 데이터를 참고했으며, 종목 선별·정렬·분석은 본 사이트의
자체 팩터 모델에 의한 것입니다.</p>
"""
    desc = (f"{name} 관련주를 가치+퀄리티 팩터로 분석. 저평가·우량 상위 종목과 "
            f"PER·PBR·ROE, 최근 수익률까지 한눈에.")
    # noindex: 테마 250개가 사실상 같은 템플릿에 숫자만 바뀌는 구조라(애드센스 "얇은 콘텐츠"
    # 지적 원인 중 하나) 검색엔진 색인에서는 빼되(noindex), 사이트 내 이용·내부링크는 그대로
    # 유지한다(follow) — sitemap.xml에서도 짝지어 제외.
    return layout(f"{name} 관련주 — 가치·퀄리티 분석 | 한국주식 팩터", desc, canonical, body,
                  noindex=True)


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
        open_attr = " open" if len(items) <= 8 else ""
        sections += (f'<details class="cat-details"{open_attr}><summary>'
                    f'{items[0]["emoji"]} <b style="font-size:15px">{_esc(label)}</b> '
                    f'<span class="muted" style="font-size:13px;font-weight:400">'
                    f'· {len(items)}개 종목</span></summary><div class="cat-body">'
                    f'<p style="margin-top:0">{_esc(_FLAG_EXPLAIN.get(label, ""))}</p>'
                    f'<div class="wrap"><table style="table-layout:fixed;width:100%">'
                    f'<colgroup><col style="width:30%"><col style="width:70%"></colgroup>'
                    f'<thead><tr><th style="text-align:left">종목</th>'
                    f'<th style="text-align:left">내용</th></tr></thead>'
                    f'<tbody>{rows}</tbody></table></div></div></details>')
    if not sections:
        sections = '<p class="muted">현재 이상신호가 감지된 종목이 없습니다.</p>'
    body = f"""
<h1>{_ic('alert')} 이상신호 리포트 <span class="muted" style="font-size:14px">({_esc(asof)} 기준)</span></h1>
<p class="muted">코스피·코스닥 전 종목 대상, 규칙 기반으로 감지된 참고 신호 전체 {total}건
(소형주 포함 · 이 중 시총 300억 미만 초소형주는 백테스트 미검증 참고용).</p>
<p>재무 데이터에서 <b>규칙 기반으로 감지된 참고 신호</b>를 모았습니다. 적자 전환, 부채비율
급증, 영업외 손익 의존, 매출 2년 연속 감소 — 4가지 유형을 자동으로 스캔합니다.
<b>회계부정을 진단하는 도구가 아니며</b>, "한번 확인해볼 만한 종목"을 걸러주는 참고 신호입니다.
매수·매도 추천이 아닙니다. 심각도(적자전환 등) 높은 유형 순으로 정렬했으며, 신호가 뜬 종목은
클릭해서 실제 재무제표·공시 원문을 직접 확인해보세요.</p>
{sections}
<p class="muted footnote">데이터: DART 최신 사업보고서. 규칙 기반 참고 신호이며 회계부정 진단이 아닙니다.
관련 → <a href="/audit-watch">감사의견 주의 종목</a> · <a href="/guides">재무 이상신호 읽는 법 가이드</a></p>
"""
    desc = f"{asof} 기준 적자전환·부채비율급증·영업외손익의존·매출감소 등 재무 이상신호가 감지된 한국 상장기업 리포트."
    return layout(f"이상신호 리포트 ({asof}) — 적자전환·부채급증 감지 기업",
                  desc, canonical, body, show_subscribe=False)


_AUDIT_ORDER = {"의견거절": 0, "부적정의견": 1, "한정의견": 2}
_AUDIT_EXPLAIN = {
    "의견거절": "감사인이 감사 범위의 큰 제약이나 중대한 불확실성 때문에 <b>‘의견을 표명하지 "
                "않겠다’</b>고 밝힌 상태입니다. 감사의견 중 가장 심각한 신호로, 상장폐지 실질심사 "
                "사유가 될 수 있습니다.",
    "부적정의견": "재무제표가 회계기준을 <b>중대하게 위반</b>해 ‘적정하지 않다’고 판단한 의견입니다. "
                  "매우 드물고 심각합니다.",
    "한정의견": "대체로 적정하지만 일부 항목에서 감사 범위 제한이나 회계기준 위반이 있어 <b>‘단서를 "
                "단’</b> 의견입니다. 어떤 항목에 단서가 붙었는지 감사보고서에서 반드시 확인해야 합니다.",
}


def render_audit_watch(items, asof, canonical):
    """감사의견이 '적정'이 아닌 종목 목록 + 해설. 회계감사의견은 다른 곳에서 잘 정리해주지
    않는 우리 사이트만의 고유 데이터 — 이를 '무엇을 확인해야 하는지' 교육 해설과 결합해
    '데이터+해설' 고유 콘텐츠로 만든다(애드센스 low-value 대응의 핵심 페이지)."""
    groups = {}
    for it in items:
        groups.setdefault(it["opinion"], []).append(it)
    order = sorted(groups.keys(), key=lambda o: _AUDIT_ORDER.get(o, 9))
    sections = ""
    for op in order:
        lst = sorted(groups[op], key=lambda s: s.get("marcap_eok") or 0, reverse=True)
        rows = "".join(
            f'<tr><td style="text-align:left"><a href="/s/{_esc(s["code"])}">{_esc(s["name"])}</a> '
            f'<span class="muted">{_esc(s["code"])}</span></td>'
            f'<td>{s["year"]}년</td>'
            f'<td style="text-align:left">{_esc(s.get("auditor") or "-")}</td></tr>' for s in lst)
        sections += (f'<h2 style="margin-bottom:6px">{_esc(op)} '
                     f'<span class="muted" style="font-size:14px;font-weight:400">· {len(lst)}개 종목</span></h2>'
                     f'<p class="muted" style="margin-top:0">{_AUDIT_EXPLAIN.get(op, "")}</p>'
                     f'<div class="wrap"><table style="table-layout:fixed;width:100%">'
                     f'<colgroup><col style="width:50%"><col style="width:14%"><col style="width:36%"></colgroup>'
                     f'<thead><tr><th style="text-align:left">종목</th><th>회계연도</th>'
                     f'<th style="text-align:left">감사인</th></tr></thead>'
                     f'<tbody>{rows}</tbody></table></div>')
    if not sections:
        sections = '<p class="muted">현재 비적정 감사의견 종목이 없습니다.</p>'
    total = len(items)
    body = f"""
<h1>{_ic('shield')} 감사의견 주의 종목 <span class="muted" style="font-size:14px">({_esc(asof)} 기준)</span></h1>
<p class="muted">코스피·코스닥 상장사 중 <b>최신 감사보고서의 감사의견이 '적정'이 아닌</b> 종목 전체
{total}곳입니다. 공시 원문을 일일이 찾지 않아도 한 곳에서 확인할 수 있습니다.</p>

<p>회계감사의견은 감사인이 <b>“재무제표가 회계기준에 맞게 작성됐는가”</b>를 판단한 결과로,
<b>적정 · 한정 · 부적정 · 의견거절</b> 네 가지가 있습니다. '적정의견'이 회사가 우량하다는 보증은
아니지만, 반대로 <b>'적정'이 아니라는 건 분명한 주의 신호</b>입니다 — 특히 <b>의견거절</b>은
상장폐지 실질심사로 이어질 수 있습니다.</p>

<div style="border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0;background:var(--panel2)">
<b>이 목록을 봤다면 무엇을 확인해야 하나</b>
<ol style="margin:8px 0 0;padding-left:20px;line-height:1.9">
<li>감사보고서의 <b>'강조사항'·'계속기업 관련 불확실성'</b> 문단을 끝까지 읽기 (왜 이런 의견인지 사유가 적혀 있습니다)</li>
<li><b>유동비율</b>(유동자산÷유동부채)과 <b>자본잠식</b> 여부 — 재무상태표에서 바로 확인</li>
<li><b>영업활동현금흐름</b>이 계속 마이너스인지 — 장부 이익과 실제 현금이 따로 노는지</li>
<li>이 의견이 <b>몇 년째 반복</b>되는지, 회사의 자구계획(증자·자산매각 등)이 실제 이행됐는지</li>
</ol>
</div>

{sections}

<p class="muted footnote">데이터: DART 최신 사업보고서·감사보고서 기준. 규칙이 아니라 실제 공시된 감사의견을
집계한 것이며, 회계부정 진단이나 매수·매도 추천이 아닙니다. 종목을 클릭하면 재무제표·감사의견
연혁을 직접 확인할 수 있습니다. 관련 → <a href="/anomaly-report">이상신호 리포트</a> ·
<a href="/guides">감사의견·리스크 읽는 법 가이드</a></p>
"""
    desc = (f"{asof} 기준 감사의견이 '적정'이 아닌(한정·부적정·의견거절) 한국 상장기업 {total}곳 "
            f"목록과 해설. 상장폐지 위험 신호 참고용.")
    return layout("감사의견 주의 종목 — 한정·부적정·의견거절 상장사 목록",
                  desc, canonical, body, show_subscribe=False)


def render_halted_stocks(rows, asof, canonical):
    """현재 거래정지 종목 모음 — 매수·매도 자체가 안 되는 종목이라 일반 랭킹·비교·섹터
    분석에서는 전부 제외하고, 여기 따로 모아 최근 공시로 재개 여부를 살펴보게 한다."""
    def disc_html(items):
        if not items:
            return '<span class="muted" style="font-size:12px">최근 공시 없음</span>'
        return "".join(
            f'<div style="font-size:12.5px;margin:3px 0"><a href="{_esc(d.get("link",""))}" '
            f'target="_blank" rel="noopener">{_esc(d.get("title",""))}</a> '
            f'<span class="muted">{_esc(d.get("date",""))}</span></div>' for d in items[:3])

    def price_cell(r):
        if r.get("last_price") is None:
            return '<span class="muted">–</span>'
        return f'{r["last_price"]:,.0f}원 <span class="muted" style="font-size:12px">({_esc(r.get("last_date") or "")})</span>'

    trs = "".join(
        f'<tr><td style="text-align:left"><a href="/s/{_esc(r["code"])}">{_esc(r["name"])}</a> '
        f'<span class="muted">{_esc(r["code"])}</span></td>'
        f'<td class="muted">{_esc(r.get("market") or "")}</td>'
        f'<td>{price_cell(r)}</td>'
        f'<td style="text-align:left">{disc_html(r.get("disclosures"))}</td></tr>' for r in rows)
    if not trs:
        trs = '<tr><td colspan=4 class="muted">현재 거래정지 종목이 없습니다.</td></tr>'

    body = f"""
<h1>{_ic('alert')} 거래정지 종목 <span class="muted" style="font-size:14px">({_esc(asof)} 기준 · {len(rows)}개)</span></h1>
<p class="muted">현재 매수·매도 자체가 불가능한 거래정지 종목만 따로 모은 페이지입니다.
이 사이트의 랭킹·조건검색·종목비교·업종분석 등 다른 모든 화면에서는 거래정지 종목을
전부 제외합니다 — 어차피 사고 팔 수 없는 종목이 팩터 점수·비교 결과에 섞여 나오면
오해를 부를 수 있어서입니다.</p>
<p>거래정지 사유는 하나가 아닙니다. 감사의견 비적정·관리종목 지정·불성실공시법인 지정처럼
투자자 보호 성격의 정지도 있고, 합병·분할·액면분할 같은 <b>단순 기업 이벤트 처리</b> 때문에
잠깐 멈추는 경우도 있습니다. 정지 자체가 곧 "위험 종목"이라는 뜻은 아니니, 아래 최근 공시를
직접 확인해서 정지 사유와 재개 여부를 판단하시기 바랍니다.</p>
<div class="wrap"><table>
<thead><tr><th style="text-align:left">종목</th><th>시장</th><th>정지 전 마지막가(정지 시작일)</th>
<th style="text-align:left">최근 공시</th></tr></thead>
<tbody>{trs}</tbody>
</table></div>
<p class="muted footnote">괄호 안 날짜는 실제 마지막 거래(거래량 0 초과)가 있었던 날로, 정지
시작 시점을 뜻합니다. 실시간 재개 여부와는 별개입니다. 공시: DART 공식 공시목록 API.
매수·매도 추천이 아닙니다.</p>
"""
    desc = f"{asof} 기준 거래정지 중인 한국 상장기업 {len(rows)}개와 최근 공시 모음. 정지 사유 확인용."
    return layout(f"거래정지 종목 ({asof}) — 정지 사유·재개 여부 확인",
                  desc, canonical, body, show_subscribe=False, noindex=True)


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
        f'<tr><td style="text-align:left"><a href="/s/{_esc(r["code"])}">{_esc(r["name"])}</a>'
        f'{_smallcap_mark(r)}</td>'
        f'<td>{"★"*r["dims"][dim_key]["stars"]}</td>'
        f'<td>{_fmt(r.get(metric_key), nd)}{unit}</td></tr>' for r in top)
    return trs or '<tr><td colspan=3 class="muted">데이터 부족</td></tr>'


def render_monthly_health(rows, anomaly_count, asof, canonical, movers_up=None, movers_down=None):
    """이번 달 건강점수 랭킹 — 종합점수 TOP20 + 4차원별 최고 TOP5."""
    top20 = sorted(rows, key=lambda r: r.get("score") or 0, reverse=True)[:20]
    top_rows = "".join(
        f'<tr><td style="text-align:left"><a href="/s/{_esc(r["code"])}">{_esc(r["name"])}</a>'
        f'{_smallcap_mark(r)} '
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
<p class="muted">코스피·코스닥 전 종목 대상, 가치+퀄리티 종합점수 TOP20과 4차원 건강검진 별점 랭킹입니다.
(시총 300억 미만 초소형주는 백테스트 미검증 참고용입니다.)</p>
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
<p class="muted">코스피·코스닥 전 종목 대상, 최근 1개월 테마 동일가중 수익률 강세·약세 순위입니다.</p>
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
        elif stripped.startswith("■"):
            # 교육글·Claude 브리핑의 ■ 소제목 → h2 (■는 이모지 범위 밖이라 별도 처리)
            out.append(f"<h2>{_esc(stripped.lstrip('■').strip())}</h2>")
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


def _article_ld(title, desc, canonical, date_str):
    """인사이트 아티클용 Article 구조화 데이터 — 브레드크럼만으로는 "이게 진짜 발행된
    기사"라는 신호가 약해서, headline/datePublished/author/publisher를 명시해 구글이
    아티클로 인식하도록 돕는다. 실제 발행 시각까진 기록해두지 않아 daily-content.yml
    실행 목표 시각(KST 07:30 전후)을 근사치로 쓴다 — 날짜 단위 신선도 신호가 목적이라
    분 단위 정확도는 중요하지 않음. 작성자는 실명 필자가 아니라 자동 분석 엔진이므로
    Person이 아닌 Organization으로 정직하게 표기."""
    parts = urlsplit(canonical)
    site = f"{parts.scheme}://{parts.netloc}"
    published = f"{date_str}T07:30:00+09:00"
    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title[:110],
        "description": desc,
        "datePublished": published,
        "dateModified": published,
        "inLanguage": "ko",
        "author": {"@type": "Organization", "name": "머니체크업", "url": f"{site}/"},
        "publisher": {"@type": "Organization", "name": "머니체크업",
                      "logo": {"@type": "ImageObject", "url": f"{site}/static/og-image.png"}},
        "image": [f"{site}/static/og-image.png"],
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
    }
    return f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>\n'


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
    return layout(title, desc, canonical, body,
                  extra_head=_article_ld(title, desc, canonical, date_str))


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


# 가이드 카테고리 → 관련 데이터/도구 페이지(3단계 상호링크). 교육 글을 읽은 뒤 우리
# 사이트의 실제 데이터로 바로 넘어가게 해서 "데이터↔교육" 콘텐츠 구조를 만든다.
_GUIDE_RELATED = {
    "리스크신호": [("/audit-watch", "감사의견 주의 종목 보기"),
                   ("/anomaly-report", "재무 이상신호 리포트")],
    "백테스트팩터": [("/backtest", "정직한 백테스트 결과"),
                     ("/", "가치+퀄리티 종목 랭킹")],
    "재무제표실전": [("/anomaly-report", "재무 이상신호 리포트"),
                     ("/audit-watch", "감사의견 주의 종목")],
    "투자기초기": [("/", "종목 랭킹·건강점수 보기")],
}


def _guide_related_html(category):
    rel = _GUIDE_RELATED.get(category)
    if not rel:
        return ""
    links = " &nbsp;·&nbsp; ".join(f'<a href="{u}">{_esc(t)} →</a>' for u, t in rel)
    return (f'<div style="border:1px solid var(--line);border-radius:10px;padding:13px 16px;'
            f'margin:22px 0 0;background:var(--panel2)">'
            f'<b>이 글과 관련된 실제 데이터</b><div style="font-size:14px;margin-top:6px;'
            f'line-height:1.9">{links}</div></div>')


def render_guide(title, category, body, slug, canonical, date_str=None):
    """개별 교육 가이드 글 페이지(에버그린). body는 파일에서 [카테고리]·제목·구분선을 뗀
    본문. 웹에선 _strip_web_tail로 CTA·면책·해시태그 꼬리를 잘라 애드센스 키워드스터핑
    신호를 피한다(면책은 layout 푸터에 이미 있음). insights 아티클과 같은 렌더 파이프."""
    from urllib.parse import quote  # noqa: F401 (slug 인코딩은 목록에서 사용)
    body_web = _strip_web_tail(body)
    body_html = _insight_body_html(body_web)
    cat = _esc(category or "가이드")
    eyebrow = f'{_ic("news")} <b>{cat}</b>' + (f' · {_insight_date_kr(date_str)}' if date_str else "")
    article = f"""
<nav class="muted" style="font-size:13px"><a href="/guides">← 투자 가이드 목록</a></nav>
<article>
<p class="muted" style="margin:8px 0 2px;font-size:12.5px;letter-spacing:.02em">{eyebrow}</p>
<h1>{_esc(title)}</h1>
{body_html}
</article>
{_guide_related_html(category)}
<div class="muted" style="margin-top:22px;font-size:13px"><a href="/guides">← 투자 가이드 목록으로</a></div>
"""
    snippet = ""
    for ln in body_web.split("\n"):
        s = ln.strip()
        if s and not s.startswith(("■", "-", "#", "※", "(", "①", "②", "③", "④", "⑤")):
            snippet = s
            break
    desc = (snippet or title)[:150]
    extra = _article_ld(title, desc, canonical, date_str) if date_str else ""
    return layout(title, desc, canonical, article, show_subscribe=False, extra_head=extra)


def render_guides_index(entries, canonical):
    """가이드 아카이브 — 카테고리별로 묶은 글 목록. entries: [{slug,title,category,snippet}]."""
    from urllib.parse import quote
    bycat = {}
    for e in entries:
        bycat.setdefault(e["category"] or "가이드", []).append(e)
    sections = ""
    for cat in sorted(bycat.keys()):
        cards = "\n".join(
            f'<a href="/guides/{quote(e["slug"])}" class="insight-card">'
            f'<div class="ic-title">{_esc(e["title"])}</div>'
            f'<div class="ic-snip muted">{_esc(e["snippet"])}</div></a>' for e in bycat[cat])
        sections += f'<h2>{_esc(cat)}</h2>{cards}'
    if not entries:
        sections = '<p class="muted">아직 발행된 가이드가 없습니다.</p>'
    body = f"""
<h1>{_ic('news')} 투자 가이드</h1>
<p>재무제표·회계감사의견·재무 이상신호처럼 <b>위험을 미리 걸러내는 데 필요한 개념</b>을,
초보도 실제로 확인하고 판단할 수 있게 단계별로 풀어쓴 교육 글 모음입니다. 특정 종목 추천이
아니라, 스스로 판단하는 힘을 기르기 위한 정보·교육용 콘텐츠예요.</p>
<style>
.insight-card{{display:block;border:1px solid #8883;border-radius:10px;padding:14px 16px;
 margin:10px 0;text-decoration:none;color:inherit;font-weight:400}}
.insight-card:hover{{border-color:#1a63cf;text-decoration:none}}
.insight-card .ic-title{{font-weight:700;font-size:15.5px;margin:0 0 3px}}
.insight-card .ic-snip{{font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
</style>
{sections}
"""
    desc = ("재무제표·회계감사의견·재무 이상신호 등 위험을 걸러내는 투자 개념을 단계별로 "
            "풀어쓴 교육 가이드 모음 — 머니체크업.")
    return layout("투자 가이드 — 재무제표·감사의견·리스크 읽는 법", desc, canonical, body)


# ── 종목 비교 ("A vs B") ────────────────────────────────────────────────────
# 검색 의도가 뚜렷한 에버그린 콘텐츠("삼성전자 vs SK하이닉스") — /s/{code}와 같은 패턴으로
# 어떤 두 종목이든 받는 범용 SSR 페이지를 만들되, sitemap엔 업종+시총으로 자동 페어링한
# '라이벌 쌍'만 큐레이션해서 올린다(app.py::_compare_pairs — 수작업 리스트업 없음).
_COMPARE_METRICS = [
    ("PER", "per", True, lambda v: f"{v:.1f}배"),
    ("PBR", "pbr", True, lambda v: f"{v:.2f}배"),
    ("ROE%", "roe", False, lambda v: f"{v:.1f}%"),
    ("영업이익률%", "op_margin", False, lambda v: f"{v:.1f}%"),
    ("부채비율%", "debt_ratio", True, lambda v: f"{v:.0f}%"),
    ("배당수익률%", "div_yield", False, lambda v: f"{v:.2f}%"),
    ("시가총액", "marcap", False, lambda v: f"{round(v/1e8):,}억"),
    ("건강점수", "score", False, lambda v: f"{v:.1f}"),
]
_COMPARE_DIM_ORDER = [("value", "밸류에이션"), ("profit", "수익성"),
                      ("safety", "안정성"), ("growth", "성장성")]


def render_compare_page(a, b, canonical):
    """a, b: get_ranking() row(dims 포함). 같은 업종·시총 상위끼리 자동 페어링된
    비교 페이지 — 표만 있으면 얇은 콘텐츠라, dims(별점)를 4차원별로 직접 비교하는
    산문 해석을 반드시 붙인다."""
    def cell(v, fmt):
        return fmt(v) if v is not None else "–"

    def winner(key, lower_better):
        va, vb = a.get(key), b.get(key)
        if va is None or vb is None or va == vb:
            return None
        if lower_better:
            return "a" if va < vb else "b"
        return "a" if va > vb else "b"

    rows_html = ""
    for label, key, lower_better, fmt in _COMPARE_METRICS:
        w = winner(key, lower_better)
        ca = ' style="font-weight:700;color:#1a63cf"' if w == "a" else ""
        cb = ' style="font-weight:700;color:#1a63cf"' if w == "b" else ""
        rows_html += (f'<tr><td style="text-align:left">{_esc(label)}</td>'
                     f'<td{ca}>{cell(a.get(key), fmt)}</td>'
                     f'<td{cb}>{cell(b.get(key), fmt)}</td></tr>')

    dims_a, dims_b = a.get("dims") or {}, b.get("dims") or {}
    verdict = []
    dims_rows_html = ""
    for key, label in _COMPARE_DIM_ORDER:
        da, db_ = dims_a.get(key), dims_b.get(key)
        sa, sb = (da or {}).get("stars"), (db_ or {}).get("stars")
        dims_rows_html += (f'<tr><td style="text-align:left">{_esc(label)}</td>'
                          f'<td>{_stars_html(sa)}</td><td>{_stars_html(sb)}</td></tr>')
        if da and db_ and sa is not None and sb is not None:
            if sa > sb:
                verdict.append(f"<b>{_esc(label)}</b>은 {_esc(a['name'])}{_josa_ga(a['name'])} 상대적으로 우위")
            elif sb > sa:
                verdict.append(f"<b>{_esc(label)}</b>은 {_esc(b['name'])}{_josa_ga(b['name'])} 상대적으로 우위")
            else:
                verdict.append(f"<b>{_esc(label)}</b>은 비슷한 수준")
    verdict_html = (", ".join(verdict) + "입니다."
                    if verdict else "두 종목의 지표를 비교할 데이터가 부족합니다.")

    sector = a.get("sector") or "기타"
    body = f"""
<h1>{_ic('barchart')} {_esc(a['name'])}{_smallcap_mark(a)} vs {_esc(b['name'])}{_smallcap_mark(b)} — 재무·밸류에이션 비교</h1>
<p class="muted">같은 업종({_esc(sector)}) 내 시가총액 상위 종목끼리 자동으로 비교한 페이지입니다.
최근 연간 재무제표·최신 시세 기준.</p>
<p>{verdict_html} (같은 유니버스·업종 내 상대 비교이며, 매수·매도 추천이 아닙니다.)</p>
<h2>건강검진 별점 비교</h2>
<div class="wrap"><table>
<thead><tr><th style="text-align:left">항목</th>
<th><a href="/s/{a['code']}">{_esc(a['name'])}</a></th>
<th><a href="/s/{b['code']}">{_esc(b['name'])}</a></th></tr></thead>
<tbody>{dims_rows_html}</tbody>
</table></div>
<h2>세부 지표</h2>
<div class="wrap"><table>
<thead><tr><th style="text-align:left">지표</th>
<th><a href="/s/{a['code']}">{_esc(a['name'])}</a></th>
<th><a href="/s/{b['code']}">{_esc(b['name'])}</a></th></tr></thead>
<tbody>{rows_html}</tbody>
</table></div>
<p class="muted footnote">파란 굵은 글씨가 해당 지표에서 더 나은 쪽입니다. 데이터: DART 최신 사업보고서·KRX 시세.
팩터점수는 코스피·코스닥 전 종목 대상 백분위 기준이며, 시총 300억 미만 초소형주는
백테스트로 검증되지 않아 참고용입니다(300억~3,000억 구간은 별도 백테스트로 검증됨).</p>
"""
    title = f"{a['name']} vs {b['name']} 비교 — PER·PBR·ROE·건강점수"
    desc = f"{a['name']}과 {b['name']}의 PER·PBR·ROE·부채비율·배당수익률·건강점수를 비교합니다."
    return layout(f"{title} | 한국주식", desc, canonical, body, show_subscribe=False)


def render_compare_index(pairs, canonical):
    """엄선된 '라이벌 쌍' 목록. pairs: [(a_row, b_row)]."""
    cards = []
    for a, b in pairs:
        cards.append(
            f'<a href="/compare/{a["code"]}/{b["code"]}" class="cmp-card">'
            f'<div class="cmp-title">{_esc(a["name"])} vs {_esc(b["name"])}</div>'
            f'<div class="cmp-sub muted">{_esc(a.get("sector") or "기타")} · '
            f'건강점수 {_fmt(a.get("score"))} vs {_fmt(b.get("score"))}</div></a>')
    cards_html = "\n".join(cards) or '<p class="muted">아직 준비된 비교가 없습니다.</p>'
    body = f"""
<h1>{_ic('barchart')} 종목 비교</h1>
<p>같은 업종 내 시가총액 상위 종목끼리 PER·PBR·ROE·부채비율·건강점수를 자동으로 비교합니다.
원하는 두 종목을 직접 비교하고 싶다면 검색으로 종목 2개를 골라보세요.</p>
<style>
.cmp-card{{display:block;border:1px solid #8883;border-radius:10px;padding:14px 16px;
 margin:10px 0;text-decoration:none;color:inherit;font-weight:400}}
.cmp-card:hover{{border-color:#1a63cf;text-decoration:none}}
.cmp-title{{font-weight:700;font-size:15.5px}}
.cmp-sub{{font-size:13px;margin-top:3px}}
</style>
{cards_html}
"""
    desc = "같은 업종 라이벌 종목끼리 PER·PBR·ROE·부채비율·건강점수를 비교하는 페이지 모음."
    return layout("종목 비교 — 라이벌 종목 재무·밸류에이션 비교", desc, canonical, body)


# ── 백테스트 방법론 딥다이브 ────────────────────────────────────────────────
# about.html#backtest에 요약으로만 있던 검증 결과를, 신뢰성(E-E-A-T) 신호를 위해
# 독립된 긴 아티클로 풀어낸다. 숫자는 about.html에 이미 게시된 것과 반드시 일치시켜야
# 하므로(다른 페이지가 다른 숫자를 말하면 오히려 신뢰가 깎임) 새로 재계산하지 않고,
# 이미 about.html에 검증·게시된 결과를 그대로 인용하되 '왜' 각 방법론 장치가 필요한지를
# 구체적 예시로 훨씬 깊게 설명한다 — 단순 재포맷이 아니라 실제 설명 깊이를 더한 원본 분석.
def render_backtest_methodology(canonical):
    body = """
<h1>{ic_target} 건강점수, 실제로 초과수익을 냈을까? — 백테스트 검증 전 과정</h1>
<p class="muted">이 페이지는 <a href="/about#backtest">소개 페이지</a>에 요약된 검증 결과를,
어떤 함정을 어떻게 통제했고 왜 그게 중요한지까지 전부 풀어서 설명합니다.</p>

<h2>왜 검증부터 했나</h2>
<p>이 사이트의 처음 아이디어는 "급등주를 자동으로 잡아 단타로 수익을 내자"는 흔한
접근이었습니다. 그런데 만들기 전에 직접 백테스트해보니, 단기 급등 스크리닝의 미약한
우위(edge)는 수수료·세금·슬리피지 같은 거래비용보다 작아서 실제로는 흑자가 나지
않았습니다. 심지어 "손절 로직을 없애니 수익이 개선"되는 것처럼 보였던 결과조차,
상장폐지된 종목이 데이터에서 통째로 빠져 있었던 <b>생존편향 착시</b>였다는 걸
나중에 알아챘습니다. 그래서 방향을 개인이 그나마 견고하게 접근할 수 있는
"저회전(연 1회) 가치+퀄리티 팩터"로 바꿨고, 이 페이지는 그 검증 과정을 숨기지 않고
전부 보여드리기 위한 것입니다.</p>

<h2>대부분의 개인 백테스트가 틀리는 이유 3가지</h2>

<h3>1) 시점정합(Point-in-Time) — "미래를 안다"는 착각 없애기</h3>
<p>예를 들어 2022년 1월에 어떤 종목을 매수할지 판단한다고 해봅시다. 순진한 백테스트는
"2022년 사업연도 재무제표"를 그때 이미 알고 있었던 것처럼 써버리는 실수를 흔히
저지릅니다 — 하지만 2022년 사업보고서는 보통 2023년 3월에야 공시됩니다. 즉 2022년
1월 시점엔 <b>2021년 재무제표가 최신 정보</b>였던 겁니다. 이 사이트의 백테스트는 각
리밸런싱 시점에 "그날 실제로 이미 공시돼 있던" 재무만 사용합니다. 이걸 안 지키면
백테스트 성과가 실제보다 좋게 부풀려집니다(look-ahead bias) — 미래의 좋은 실적을
미리 알고 산 것처럼 계산되기 때문입니다.</p>

<h3>2) 상장폐지 포함 — 사라진 회사도 계산에 넣기</h3>
<p>지금 화면에 보이는 종목 리스트만 갖고 과거를 되짚으면, 그 사이 상장폐지된 부실
기업들은 애초에 목록에 없으니 백테스트 결과에서 조용히 빠집니다. 이러면 "그때도
좋은 종목만 골랐다"는 착시가 생기는데, 사실은 <b>나쁜 종목이 사라져서 안 보이는
것</b>뿐입니다(생존편향). 이 사이트의 백테스트는 그 시점엔 분명히 살아있었던
상장폐지 종목까지 포함시켜, 폐지로 인한 손실을 결과에 그대로 반영합니다.</p>

<h3>3) 거래비용 반영 — 이론과 실전의 차이</h3>
<p>수수료·증권거래세·슬리피지(체결가와 주문가의 차이)를 매수·매도 왕복 기준으로
빠짐없이 차감합니다. 배당은 세후 총수익 기준으로 더합니다. 이 비용을 빼먹으면,
특히 회전율이 높은 전략일수록 실제로는 마이너스인 전략이 종이 위에서는 플러스로
보이는 착시가 생깁니다.</p>

<h2>핵심 결과 (요약)</h2>
<p>시점정합·상장폐지 포함·거래비용·배당을 전부 반영한 가장 엄격한 조건에서, 가치+퀄리티
포트폴리오는 동일가중 유니버스 평균을 <b>연 약 +3%포인트</b> 상회했습니다 — 특히 하락장에서
방어적인 특성을 보였습니다. 배당을 포함한 절대수익 기준으로는 시장(코스피)도 근소하게
앞섰습니다. 다만 절대 수익률 자체는 높지 않았고, 특정 해(테마 랠리가 강했던 구간)에는
오히려 크게 뒤처지기도 했습니다.</p>

<h2>정직한 한계</h2>
<p>과거 주식수를 완전히 확보하지 못해 시가총액은 근사치를 씁니다. 이 검증은 시총 3,000억
이상 중대형 종목만 대상입니다(300억~3,000억 구간은 아래 별도 검증 참고, 300억 미만
초소형주는 여전히 미검증). 상장폐지 종목은 마지막 체결가로 청산 처리해 실제보다 청산가치가
다소 높게 잡힐 수 있습니다. 그리고 무엇보다, <b>과거 성과가 미래 수익을 보장하지 않습니다.</b>
이 검증은 "완전히 안전하다"는 증명이 아니라, "최소한 흔한 착시들에 속지는 않았다"는 확인입니다.</p>

<h2>소형주(300억~3,000억)는 어떨까 — 별도 검증</h2>
<p>메인 검증의 가장 큰 한계였던 "소형 가치주는 범위 밖"이라는 지적에 답하기 위해, 시총
300억~3,000억 구간만 따로 떼어 같은 방법론(시점정합·상장폐지 포함·거래비용·배당 반영)으로
2018~2024년(7년) 백테스트했습니다. 결과: 전략 CAGR <b>+1.9%</b>로 유니버스 동일가중
(CAGR -2.0%)과 코스피(CAGR +0.4%)를 모두 앞섰고, 연평균 초과수익은 +4.0%포인트,
7년 중 4년에서 유니버스를 이겼습니다. 소형주 구간에서도 팩터 로직이 통했다는 뜻이라,
이 사이트는 시총 300억 이상 종목까지 "검증된" 범위로 다루고, 300억 미만 초소형주만
"참고용·미검증"으로 별도 표시합니다.</p>

<h2>그래서 지금 이 사이트는 무엇을 하나</h2>
<p>이 검증을 거친 팩터 로직을 <a href="/">건강점수</a>로 매일 계산해서 보여드립니다.
예측이나 자동매매가 아니라, 데이터로 판단을 돕는 리서치 도구를 지향합니다. 개별
종목의 건강점수·이상신호·회계감사의견은 <a href="/">홈</a>에서, 방법론 전체 설명은
<a href="/about#backtest">소개 페이지</a>에서 확인하실 수 있습니다.</p>
<p class="muted footnote">※ 이 페이지는 공개 데이터를 정리한 정보 제공용 콘텐츠이며, 특정 종목에
대한 매수·매도 추천이 아닙니다. 투자 판단과 책임은 본인에게 있습니다.</p>
""".format(ic_target=_ic("target"))
    title = "건강점수 백테스트 검증 — 시점정합·생존편향 제거·거래비용까지 반영한 결과"
    desc = "가치+퀄리티 건강점수가 실제로 초과수익을 냈는지, 시점정합·생존편향·거래비용까지 반영해 검증한 전 과정."
    return layout(title, desc, canonical, body)


# ── 섹터 로테이션 리뷰 ───────────────────────────────────────────────────────
# 사용자 요청: "이번 분기는 어느 섹터가 강했나"를 factor/sector_rotation.py의 연도별
# 백테스트 데이터로 우려내되, 실제 파일은 연도 단위(2018~)이지 분기 단위가 아니라서
# '분기별 시계열'이라고 과장하지 않는다 — 대신 (1) 현재 스냅샷은 app.py::
# _sector_quarterly_perf()로 방금 계산한 진짜 최근 3개월치, (2) 역대 흐름은 실제
# 있는 연도별 데이터를 정직하게 인용하는 두 축으로 구성한다.
def render_sector_rotation_review(current_perf, history, canonical):
    top = [p for p in current_perf if p["ret_3m"] is not None][:5]
    bottom = [p for p in current_perf if p["ret_3m"] is not None][-5:][::-1]

    def row(p):
        r1 = f"{p['ret_1m']:+.1f}%" if p["ret_1m"] is not None else "–"
        r3 = f"{p['ret_3m']:+.1f}%" if p["ret_3m"] is not None else "–"
        return (f'<tr><td style="text-align:left">{_esc(p["sector"])}</td>'
               f'<td>{r1}</td><td>{r3}</td><td class="muted">{p["count"]}</td></tr>')

    lead = top[0] if top else None
    lag = bottom[0] if bottom else None
    lead_txt = (f"최근 3개월 기준 <b>{_esc(lead['sector'])}</b>이 {lead['ret_3m']:+.1f}%로 "
               f"가장 강했고, " if lead else "")
    lag_txt = (f"<b>{_esc(lag['sector'])}</b>이 {lag['ret_3m']:+.1f}%로 가장 부진했습니다."
              if lag else "")

    history_html = ""
    if history:
        from collections import Counter
        best = history.get("best", {})
        wins = Counter(best.values())
        top_hist = wins.most_common(5)
        years_line = " · ".join(f"{y}년 {_esc(s)}" for y, s in sorted(best.items(), reverse=True)[:5])
        hist_rows = "".join(
            f'<tr><td style="text-align:left">{_esc(s)}</td><td>{n}회</td></tr>'
            for s, n in top_hist)
        history_html = f"""
<h2>역대 흐름은 어땠나 (2018년~)</h2>
<p>최근 연도별 최강 섹터: {years_line}. {history.get('years', [None])[0]}년부터 지금까지
연간 1위를 가장 많이 차지한 섹터는 다음과 같습니다.</p>
<div class="wrap"><table>
<thead><tr><th style="text-align:left">섹터</th><th>연간 1위 횟수</th></tr></thead>
<tbody>{hist_rows}</tbody></table></div>
<p class="muted">이 표는 <a href="/api/sectors">시점정합·상장폐지 포함 백테스트</a>로 검증한
연도별(2018~) 결과입니다. 자세한 검증 방법은 <a href="/backtest">백테스트 방법론</a> 참고.</p>
"""

    body = f"""
<h1>{_ic('refresh')} 이번 분기 국내 증시, 어느 섹터가 강했나 — 섹터 로테이션 리뷰</h1>
<p class="muted">최근 3개월(약 63거래일) 기준, 섹터(17개 대분류)별 시가총액 상위 10종목
동일가중 수익률입니다. {lead_txt}{lag_txt}</p>

<h2>이번 분기 섹터 성과 TOP5 · 부진 TOP5</h2>
<div class="wrap"><table>
<thead><tr><th style="text-align:left">섹터</th><th>1개월</th><th>3개월</th><th>종목수</th></tr></thead>
<tbody>{"".join(row(p) for p in top)}</tbody></table></div>
<h3 style="margin-top:22px">부진 섹터</h3>
<div class="wrap"><table>
<thead><tr><th style="text-align:left">섹터</th><th>1개월</th><th>3개월</th><th>종목수</th></tr></thead>
<tbody>{"".join(row(p) for p in bottom)}</tbody></table></div>
{history_html}
<h2>섹터 로테이션을 왜 보나</h2>
<p>시장 전체가 오르내리는 국면에서도, 그 안에서 자금이 몰리는 섹터는 계속 바뀝니다("로테이션").
한 섹터가 몇 년 연속 1위를 차지하기도 하고, 반대로 오래 부진하던 섹터가 갑자기 반등하기도
합니다. 개별 종목보다 섹터 단위 흐름을 먼저 보면, 지금 시장이 어떤 이야기를 하고 있는지
큰 그림을 잡는 데 도움이 됩니다.</p>
<p>개별 종목의 건강점수·재무제표는 <a href="/">홈</a>에서, 같은 업종 라이벌끼리 직접 비교는
<a href="/compare">종목 비교</a>에서 확인하실 수 있습니다.</p>
<p class="muted footnote">※ 이 페이지는 공개 데이터를 정리한 정보 제공용 콘텐츠이며, 특정 섹터나
종목에 대한 매수·매도 추천이 아닙니다. 과거 성과가 미래 수익을 보장하지 않습니다.</p>
"""
    desc = "국내 증시 섹터별 최근 3개월 수익률과 2018년 이후 연도별 로테이션 패턴을 정리했습니다."
    return layout("섹터 로테이션 리뷰 — 이번 분기 강세·부진 업종 정리", desc, canonical, body)
