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
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{_esc(canonical)}">
<meta property="og:type" content="article"><meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}"><meta property="og:locale" content="ko_KR">
<style>
body{{max-width:900px;margin:0 auto;padding:20px 18px 60px;line-height:1.7;
 font-family:-apple-system,"Segoe UI",Roboto,"Malgun Gothic",sans-serif;color:#1a2028;background:#fff}}
@media (prefers-color-scheme:dark){{body{{background:#0f1216;color:#e6ebf1}}a{{color:#4f9dff}}
 th{{color:#93a1b0}} tr:hover{{background:#171c23}} .muted{{color:#93a1b0}}}}
a{{color:#1f6fe0;text-decoration:none}}a:hover{{text-decoration:underline}}
h1{{font-size:23px}}h2{{font-size:18px;margin-top:28px}}
nav{{font-size:13px;margin-bottom:14px}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin:10px 0}}
th,td{{padding:7px 9px;border-bottom:1px solid #8883;text-align:right;white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}
.wrap{{overflow-x:auto}} .muted{{color:#5e6b79}} .pos{{color:#1a9e63}} .neg{{color:#d23b41}}
.badge{{display:inline-block;padding:1px 8px;border-radius:10px;background:#8881;font-size:12px;margin:2px 3px 0 0}}
footer{{margin-top:32px;padding-top:16px;border-top:1px solid #8883;font-size:12px;color:#888}}
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
        if s.get("in_rank"):
            out += (f'<tr><td><a href="/">{_esc(s["name"])}</a> '
                    f'<span class="muted">{_esc(s["code"])}</span></td>'
                    f'<td><b>{_fmt(s.get("score"),1)}</b></td><td>{_fmt(s.get("per"))}</td>'
                    f'<td>{_fmt(s.get("pbr"),2)}</td><td>{_fmt(s.get("roe"))}</td>'
                    f'<td class="muted">{_esc(s.get("sector") or "")}</td></tr>')
        else:
            out += (f'<tr><td>{_esc(s["name"])} <span class="muted">{_esc(s["code"])}</span></td>'
                    f'<td class="muted">–</td><td class="muted">–</td><td class="muted">–</td>'
                    f'<td class="muted">–</td><td class="muted"></td></tr>')
    return out


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
<tbody>{_stock_rows(sorted(stocks, key=lambda s:(s.get("in_rank",False), s.get("score") or 0), reverse=True))}</tbody>
</table></div>
<p class="muted">※ 팩터점수는 시총 3,000억 이상 유니버스 내 백분위 기준. 재무=DART 최신
사업보고서. 테마 분류는 공개 테마 데이터를 참고했으며, 종목 선별·정렬·분석은 본 사이트의
자체 팩터 모델에 의한 것입니다.</p>
"""
    desc = (f"{name} 관련주를 가치+퀄리티 팩터로 분석. 저평가·우량 상위 종목과 "
            f"PER·PBR·ROE, 최근 수익률까지 한눈에.")
    return layout(f"{name} 관련주 — 가치·퀄리티 분석 | 한국주식 팩터", desc, canonical, body)


def render_weekly(strong, weak, top_value, asof, canonical):
    def theme_li(t):
        cls = "pos" if (t["ret_1m"] or 0) >= 0 else "neg"
        return (f'<tr><td><a href="/t/{t["no"]}">{_esc(t["name"])}</a></td>'
                f'<td class="{cls}">{_fmt(t["ret_1m"])}</td>'
                f'<td>{_fmt(t["ret_3m"])}</td><td class="muted">{t["priced"]}/{t["count"]}</td></tr>')
    strong_rows = "".join(theme_li(t) for t in strong)
    weak_rows = "".join(theme_li(t) for t in weak)
    val_rows = "".join(
        f'<tr><td>{_esc(s["name"])} <span class="muted">{_esc(s["code"])}</span></td>'
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
