# -*- coding: utf-8 -*-
"""
SEO용 서버렌더 원본 콘텐츠 (테마 관련주 랜딩페이지 · 주간 시장 코멘터리).

스크랩 데이터를 그대로 옮기지 않고, 우리 팩터점수·밸류에이션·정렬·코멘트를 얹어
'원본 분석'으로 만든다. 크롤링 가능한 텍스트+표.
"""
from __future__ import annotations
import html


def _esc(s):
    return html.escape(str(s if s is not None else ""))


def _fmt(v, nd=1):
    if v is None:
        return "–"
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "–"


def layout(title, desc, canonical, body, extra_nav=""):
    return f"""<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="google-site-verification" content="5TVrZ_HlWRfb6pGJ1o-2YwzL1qnPxqpTwJSLWVGLM74" />
<meta name="naver-site-verification" content="2f945cfe349bbdceb4341472d7d2a1cc69b26a1f" />
<title>MN_SCAN 머니탐지 · {_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{_esc(canonical)}">
<meta property="og:type" content="article"><meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}"><meta property="og:locale" content="ko_KR">
<link rel="stylesheet" as="style" crossorigin
  href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css">
<style>
body{{max-width:900px;margin:0 auto;padding:20px 18px 60px;line-height:1.75;font-size:15.5px;
 font-family:'Pretendard Variable',Pretendard,-apple-system,"Segoe UI",Roboto,
 "Apple SD Gothic Neo","Malgun Gothic",sans-serif;color:#12161c;background:#fff}}
@media (prefers-color-scheme:dark){{body{{background:#0f1216;color:#f1f4f8}}a{{color:#6fb0ff}}
 th{{color:#aab6c2}} tr:hover{{background:#171c23}} .muted{{color:#aab6c2}}}}
a{{color:#1a63cf;text-decoration:none;font-weight:600}}a:hover{{text-decoration:underline}}
h1{{font-size:24px}}h2{{font-size:19px;margin-top:28px}}
nav{{font-size:14px;margin-bottom:14px}}
table{{border-collapse:collapse;width:100%;font-size:14.5px;margin:10px 0}}
th,td{{padding:8px 10px;border-bottom:1px solid #8883;text-align:right;white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}
.wrap{{overflow-x:auto}} .muted{{color:#4a5563}} .pos{{color:#178a56}} .neg{{color:#c8333a}}
.badge{{display:inline-block;padding:1px 8px;border-radius:10px;background:#8881;font-size:12.5px;margin:2px 3px 0 0}}
.dimgrid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:10px 0}}
@media(max-width:560px){{.dimgrid{{grid-template-columns:1fr}}}}
.dimcard{{border:1px solid #8883;border-radius:10px;padding:12px 14px;background:#8880.06}}
.dimhead{{font-weight:700;font-size:14.5px;display:flex;justify-content:space-between}}
.dimstars{{color:#e0a500;letter-spacing:1px;font-size:13px}}
.dimlabel{{font-size:12.5px;color:#4a5563;margin:2px 0 4px}}
.dimtext{{font-size:13.5px;margin:0;line-height:1.6}}
footer{{margin-top:32px;padding-top:16px;border-top:1px solid #8883;font-size:13px;color:#5a6472}}
</style></head><body>
<nav><a href="/">← 대시보드</a> · <a href="/weekly">주간 리포트</a> · <a href="/themes-index">테마 전체</a> · <a href="/about">소개·면책</a>{extra_nav}</nav>
{body}
<footer>본 콘텐츠는 공개 데이터를 정량 분석한 <b>정보 제공·교육용</b>이며 특정 종목의 매수·매도
권유가 아닙니다. 데이터는 오류·지연이 있을 수 있고, 과거 성과는 미래를 보장하지 않습니다.
투자 판단과 책임은 이용자 본인에게 있습니다. · <a href="/about#privacy">개인정보처리방침</a>
· <a href="/about#disclaimer">면책조항</a></footer>
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
    color = "#178a56" if last >= first else "#c8333a"
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


_DIM_META = {"value": ("💰", "밸류에이션"), "profit": ("📈", "수익성"),
             "safety": ("🛡️", "안정성"), "growth": ("🌱", "성장성")}


def _stars_html(n):
    if n is None:
        return '<span class="muted">–</span>'
    return "★" * n + '<span class="muted">' + "☆" * (5 - n) + "</span>"


def _dims_html(dims):
    if not dims:
        return ""
    cards = ""
    for key, (emoji, label) in _DIM_META.items():
        d = dims.get(key) or {}
        cards += (f'<div class="dimcard"><div class="dimhead">{emoji} {label} '
                  f'<span class="dimstars">{_stars_html(d.get("stars"))}</span></div>'
                  f'<div class="dimlabel">{_esc(d.get("label"))}</div>'
                  f'<p class="dimtext">{_esc(d.get("text"))}</p></div>')
    overall = dims.get("overall_text") or ""
    return (f'<h2>기업 건강검진 <span class="muted" style="font-size:13px;font-weight:400">'
            f'· 같은 업종·시총 내 상대 평가</span></h2>'
            f'<div class="dimgrid">{cards}</div>'
            + (f'<p class="muted">{_esc(overall)}</p>' if overall else ""))


def _flags_html(flags):
    if flags is None:
        return ""
    if not flags:
        return ('<h2>🚩 참고할 점</h2><p class="muted">규칙 기반으로 확인한 특별한 '
                '재무 이상신호는 없습니다. (회계부정 진단이 아닌 참고 신호입니다)</p>')
    items = "".join(f'<p style="margin:6px 0">{f["emoji"]} <b>{_esc(f["label"])}</b> — '
                    f'{_esc(f["text"])}</p>' for f in flags)
    return (f'<h2>🚩 참고할 점 <span class="muted" style="font-size:13px;font-weight:400">'
            f'· 규칙 기반 참고 신호, 회계부정 진단 아님</span></h2>{items}')


def _disclosures_html(items):
    if not items:
        return '<h2>📄 공시자료</h2><p class="muted">최근 공시 데이터를 불러올 수 없습니다.</p>'
    rows = "".join(
        f'<p style="margin:6px 0"><a href="{_esc(d["link"])}" target="_blank" '
        f'rel="noopener">{_esc(d["title"])}</a> '
        f'<span class="muted" style="font-size:12px">{_esc(d.get("date"))} · '
        f'{_esc(d.get("submitter"))}</span></p>' for d in items)
    return (f'<h2>📄 공시자료 <span class="muted" style="font-size:13px;font-weight:400">'
            f'· DART 전자공시 원문</span></h2>{rows}')


def render_stock_page(code, name, summary, financials, prices, news, themes,
                      disclosures, period_returns, canonical):
    def eok(v):
        return "–" if v is None else f"{round(v/1e8):,}"
    head = f'<h1>{_esc(name)} <span class="muted" style="font-size:15px">{_esc(code)}</span></h1>'
    head += '<p class="muted">재무제표·건강검진 점수·밸류에이션과 관련 뉴스를 한 페이지에서.</p>'
    kpi = ""
    dims_html = ""
    if summary:
        kpi = (f'<p>가치+퀄리티 종합점수 <b>{_fmt(summary.get("score"))}</b> · '
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
<h1>{_esc(name)} 관련주 — 가치·퀄리티 분석</h1>
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
<p class="muted">※ 팩터점수는 시총 3,000억 이상 유니버스 내 백분위 기준. 재무=DART 최신
사업보고서. 테마 분류는 공개 테마 데이터를 참고했으며, 종목 선별·정렬·분석은 본 사이트의
자체 팩터 모델에 의한 것입니다.</p>
"""
    desc = (f"{name} 관련주를 가치+퀄리티 팩터로 분석. 저평가·우량 상위 종목과 "
            f"PER·PBR·ROE, 최근 수익률까지 한눈에.")
    return layout(f"{name} 관련주 — 가치·퀄리티 분석 | 한국주식 팩터", desc, canonical, body)


_FLAG_EXPLAIN = {
    "적자 전환": "전년에는 순이익이 흑자였는데 올해는 적자로 바뀐 경우입니다. "
                "일시적 요인(자산매각 손실, 구조조정 등)인지 본업 악화인지 재무제표를 "
                "직접 확인해볼 필요가 있습니다.",
    "영업외 손익 의존": "본업(영업활동)에서는 손실이 났지만 자산매각·투자수익 등"
                     "영업외 요인 덕에 최종 순이익은 흑자로 나온 경우입니다. "
                     "본업 경쟁력과 별개로 순이익만 보면 실제보다 좋아 보일 수 있습니다.",
    "부채비율 급증": "1년 사이 부채비율이 50%p 이상 급격히 늘었습니다. 대규모 투자·차입,"
                  " 인수합병, 실적 악화로 인한 자본 감소 등 원인을 확인해볼 필요가 있습니다.",
    "매출 2년 연속 감소": "최근 2개 회계연도 모두 매출이 전년보다 줄었습니다. "
                      "업종 전반의 불황인지, 개별 기업의 경쟁력 약화인지 살펴볼 필요가 있습니다.",
}


def render_anomaly_report(grouped, asof, canonical):
    """flags(이상신호)가 감지된 종목을 유형별로 모은 리포트."""
    total = sum(len(v) for v in grouped.values())
    sections = ""
    for label, items in grouped.items():
        rows = "".join(
            f'<tr><td style="text-align:left"><a href="/s/{_esc(s["code"])}">{_esc(s["name"])}</a> '
            f'<span class="muted">{_esc(s["code"])}</span></td>'
            f'<td style="text-align:left">{_esc(s["text"])}</td></tr>' for s in items)
        sections += (f'<h2>{items[0]["emoji"]} {_esc(label)} <span class="muted" '
                    f'style="font-size:13px;font-weight:400">· {len(items)}개 종목</span></h2>'
                    f'<p>{_esc(_FLAG_EXPLAIN.get(label, ""))}</p>'
                    f'<div class="wrap"><table><thead><tr><th style="text-align:left">종목</th>'
                    f'<th style="text-align:left">내용</th></tr></thead>'
                    f'<tbody>{rows}</tbody></table></div>')
    if not sections:
        sections = '<p class="muted">현재 이상신호가 감지된 종목이 없습니다.</p>'
    body = f"""
<h1>이상신호 리포트 <span class="muted" style="font-size:14px">({_esc(asof)} 기준)</span></h1>
<p>재무 데이터에서 <b>규칙 기반으로 감지된 참고 신호</b>를 모았습니다. 적자 전환, 부채비율
급증, 영업외 손익 의존, 매출 2년 연속 감소 — 4가지 유형을 자동으로 스캔합니다.
<b>회계부정을 진단하는 도구가 아니며</b>, "한번 확인해볼 만한 종목"을 걸러주는 참고 신호입니다.
매수·매도 추천이 아닙니다.</p>
<p class="muted">전체 {total}건 감지 (시총 3,000억 이상 유니버스 기준)</p>
{sections}
"""
    desc = f"{asof} 기준 적자전환·부채비율급증·영업외손익의존·매출감소 등 재무 이상신호가 감지된 한국 상장기업 리포트."
    return layout(f"이상신호 리포트 ({asof}) — 적자전환·부채급증 감지 기업",
                  desc, canonical, body)


_DIM_LABELS = [("value", "💰", "밸류에이션"), ("profit", "📈", "수익성"),
              ("safety", "🛡️", "안정성"), ("growth", "🌱", "성장성")]


def _dim_leader_table(rows, dim_key):
    scored = [r for r in rows if r.get("dims", {}).get(dim_key, {}).get("stars") is not None]
    scored.sort(key=lambda r: (r["dims"][dim_key]["stars"], r.get("score") or 0), reverse=True)
    top = scored[:5]
    trs = "".join(
        f'<tr><td style="text-align:left"><a href="/s/{_esc(r["code"])}">{_esc(r["name"])}</a></td>'
        f'<td>{"★"*r["dims"][dim_key]["stars"]}</td></tr>' for r in top)
    return trs or '<tr><td colspan=2 class="muted">데이터 부족</td></tr>'


def render_monthly_health(rows, anomaly_count, asof, canonical):
    """이번 달 건강점수 랭킹 — 종합점수 TOP20 + 4차원별 최고 TOP5."""
    top20 = sorted(rows, key=lambda r: r.get("score") or 0, reverse=True)[:20]
    top_rows = "".join(
        f'<tr><td style="text-align:left"><a href="/s/{_esc(r["code"])}">{_esc(r["name"])}</a> '
        f'<span class="muted">{_esc(r["code"])}</span></td><td><b>{_fmt(r.get("score"))}</b></td>'
        f'<td>{_fmt(r.get("per"))}</td><td>{_fmt(r.get("pbr"),2)}</td>'
        f'<td>{_fmt(r.get("roe"))}</td></tr>' for r in top20)
    dim_sections = ""
    for key, emoji, label in _DIM_LABELS:
        dim_sections += (f'<h3>{emoji} {label} 최고 TOP5</h3>'
                         f'<div class="wrap"><table><thead><tr><th style="text-align:left">종목</th>'
                         f'<th>별점</th></tr></thead><tbody>{_dim_leader_table(rows, key)}'
                         f'</tbody></table></div>')
    body = f"""
<h1>🎯 이번 달 건강점수 랭킹 <span class="muted" style="font-size:14px">({_esc(asof)} 기준)</span></h1>
<p>가치+퀄리티 종합점수와, 밸류에이션·수익성·안정성·성장성 4차원 건강검진 별점을 기준으로
이번 달 상위 기업을 정리했습니다. 매수·매도 추천이 아니라 <b>같은 유니버스 내 상대 비교</b>
스냅샷입니다.</p>

<h2>🏆 종합점수 TOP20</h2>
<div class="wrap"><table><thead><tr><th style="text-align:left">종목</th><th>점수</th>
<th>PER</th><th>PBR</th><th>ROE%</th></tr></thead><tbody>{top_rows}</tbody></table></div>

<h2>차원별 최고 기업</h2>
{dim_sections}

<h2>🚩 참고: 이상신호</h2>
<p>이번 달 재무 이상신호(적자전환·부채급증 등)가 감지된 종목은 <b>{anomaly_count}개</b>입니다.
<a href="/anomaly-report">→ 이상신호 리포트 전체 보기</a></p>
"""
    desc = f"{asof} 기준 가치+퀄리티 건강점수 TOP20과 밸류에이션·수익성·안정성·성장성 4차원 최고 기업 랭킹."
    return layout(f"이번 달 건강점수 랭킹 ({asof}) — 종합점수 TOP20 + 4차원 우수기업",
                  desc, canonical, body)


def render_weekly(strong, weak, top_value, asof, canonical):
    def theme_li(t):
        cls = "pos" if (t["ret_1m"] or 0) >= 0 else "neg"
        return (f'<tr><td><a href="/t/{t["no"]}">{_esc(t["name"])}</a></td>'
                f'<td class="{cls}">{_fmt(t["ret_1m"])}</td>'
                f'<td>{_fmt(t["ret_3m"])}</td><td class="muted">{t["priced"]}/{t["count"]}</td></tr>')
    strong_rows = "".join(theme_li(t) for t in strong)
    weak_rows = "".join(theme_li(t) for t in weak)
    val_rows = "".join(
        f'<tr><td><a href="/s/{s["code"]}">{_esc(s["name"])}</a> '
        f'<span class="muted">{_esc(s["code"])}</span></td>'
        f'<td><b>{_fmt(s["score"])}</b></td><td>{_fmt(s.get("per"))}</td>'
        f'<td>{_fmt(s.get("pbr"),2)}</td><td>{_fmt(s.get("roe"))}</td>'
        f'<td class="muted">{_esc(s.get("sector") or "")}</td></tr>' for s in top_value)
    top_theme = strong[0]["name"] if strong else "–"

    body = f"""
<h1>주간 한국주식 시장 리포트 <span class="muted" style="font-size:14px">({_esc(asof)} 기준)</span></h1>
<p>최근 1개월 기준 가장 강했던 테마는 <b>{_esc(top_theme)}</b> 입니다. 아래는 테마별
구성종목 동일가중 수익률로 본 강세·약세 순위와, 가치+퀄리티 팩터 상위 종목입니다.
매매 추천이 아니라 데이터로 본 흐름 정리입니다.</p>

<h2>🔥 강세 테마 TOP 10 (최근 1개월)</h2>
<div class="wrap"><table><thead><tr><th>테마</th><th>1개월%</th><th>3개월%</th><th>종목수</th></tr></thead>
<tbody>{strong_rows}</tbody></table></div>

<h2>❄️ 약세 테마 (최근 1개월)</h2>
<div class="wrap"><table><thead><tr><th>테마</th><th>1개월%</th><th>3개월%</th><th>종목수</th></tr></thead>
<tbody>{weak_rows}</tbody></table></div>

<h2>💎 가치+퀄리티 팩터 상위 종목</h2>
<p class="muted">저평가(가치) + 우량(퀄리티) 종합점수 상위. 시총 3,000억 이상.</p>
<div class="wrap"><table><thead><tr><th>종목</th><th>점수</th><th>PER</th><th>PBR</th><th>ROE%</th><th>섹터</th></tr></thead>
<tbody>{val_rows}</tbody></table></div>
<p class="muted">데이터: FinanceDataReader·DART·공개 테마/뉴스 피드. 분석·정렬은 자체 팩터 모델.</p>
"""
    desc = (f"{asof} 기준 한국주식 주간 리포트 — 최근 1개월 강세/약세 테마와 "
            f"가치+퀄리티 팩터 상위 종목 정리.")
    return layout(f"주간 한국주식 시장 리포트 ({asof}) — 강세 테마·저평가 우량주",
                  desc, canonical, body)
