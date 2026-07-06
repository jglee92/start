# -*- coding: utf-8 -*-
"""
업종별 밸류에이션 리포트. 테마 페이지(모멘텀 관점)와 달리 밸류(저평가·우량) 관점.
이미 계산된 랭킹(RANK)만으로 만들며 추가 수집이 필요 없다.
"""
from __future__ import annotations
from content import layout, _esc, _fmt
from factor.sectors import SLUGS, SLUG_TO_SECTOR


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def compute_market_avg(rk):
    return {
        "per": _avg([r.get("per") for r in rk if r.get("per") and r["per"] > 0]),
        "pbr": _avg([r.get("pbr") for r in rk]),
        "roe": _avg([r.get("roe") for r in rk]),
        "debt_ratio": _avg([r.get("debt_ratio") for r in rk]),
        "count": len(rk),
    }


def compute_sector_stats(rk, sector_name):
    rows = [r for r in rk if (r.get("sector") or "기타") == sector_name]
    stats = {
        "sector": sector_name, "count": len(rows),
        "per": _avg([r.get("per") for r in rows if r.get("per") and r["per"] > 0]),
        "pbr": _avg([r.get("pbr") for r in rows]),
        "roe": _avg([r.get("roe") for r in rows]),
        "debt_ratio": _avg([r.get("debt_ratio") for r in rows]),
        "top_score": sorted(rows, key=lambda r: r.get("score") or 0, reverse=True)[:10],
        "cheap": sorted([r for r in rows if r.get("per")],
                       key=lambda r: r["per"])[:5],
        "quality": sorted([r for r in rows if r.get("roe") is not None],
                         key=lambda r: r["roe"], reverse=True)[:5],
    }
    return stats


def _cmp_word(v, avg, lower_better):
    if v is None or avg is None:
        return ""
    higher = v > avg
    good = (not higher) if lower_better else higher
    return "높은" if higher else "낮은", "양호" if good else "저조"


def _stock_row(r):
    return (f'<tr><td style="text-align:left"><a href="/s/{_esc(r["code"])}">{_esc(r["name"])}</a> '
            f'<span class="muted">{_esc(r["code"])}</span></td>'
            f'<td><b>{_fmt(r.get("score"))}</b></td><td>{_fmt(r.get("per"))}</td>'
            f'<td>{_fmt(r.get("pbr"),2)}</td><td>{_fmt(r.get("roe"))}</td></tr>')


def render_sector_report(sector_name, stats, market_avg, canonical):
    slug = SLUGS.get(sector_name, "")
    per_dir, per_eval = _cmp_word(stats["per"], market_avg["per"], lower_better=True) or ("", "")
    roe_dir, roe_eval = _cmp_word(stats["roe"], market_avg["roe"], lower_better=False) or ("", "")
    debt_dir, debt_eval = _cmp_word(stats["debt_ratio"], market_avg["debt_ratio"], lower_better=True) or ("", "")

    summary = ""
    if stats["per"] is not None and market_avg["per"] is not None:
        summary += (f"이 업종의 평균 PER은 <b>{stats['per']:.1f}배</b>로 전체 시장 평균"
                    f"({market_avg['per']:.1f}배)보다 {per_dir}편입니다({per_eval} 밸류에이션). ")
    if stats["roe"] is not None and market_avg["roe"] is not None:
        summary += (f"평균 ROE는 <b>{stats['roe']:.1f}%</b>로 시장 평균({market_avg['roe']:.1f}%)"
                    f"보다 {roe_dir} 편이고, ")
    if stats["debt_ratio"] is not None and market_avg["debt_ratio"] is not None:
        summary += (f"평균 부채비율은 <b>{stats['debt_ratio']:.0f}%</b>로 시장 평균"
                    f"({market_avg['debt_ratio']:.0f}%)보다 {debt_dir} 편입니다.")

    top_rows = "".join(_stock_row(r) for r in stats["top_score"])
    cheap_names = ", ".join(f'<a href="/s/{_esc(r["code"])}">{_esc(r["name"])}</a>(PER {_fmt(r["per"])})'
                            for r in stats["cheap"]) or "데이터 부족"
    quality_names = ", ".join(f'<a href="/s/{_esc(r["code"])}">{_esc(r["name"])}</a>(ROE {_fmt(r["roe"])}%)'
                              for r in stats["quality"]) or "데이터 부족"

    body = f"""
<h1>📊 {_esc(sector_name)} 업종 밸류에이션 리포트</h1>
<p class="muted">시총 3,000억 이상 상장기업 {stats['count']}개 기준. 테마(모멘텀) 관점이 아닌
<b>밸류에이션(저평가·우량) 관점</b>의 업종 분석입니다.</p>
<p>{summary}</p>

<h2>저평가 상위 (PER 낮은 순)</h2>
<p>{cheap_names}</p>

<h2>우량 상위 (ROE 높은 순)</h2>
<p>{quality_names}</p>

<h2>가치+퀄리티 종합점수 TOP10</h2>
<div class="wrap"><table><thead><tr><th style="text-align:left">종목</th>
<th>점수</th><th>PER</th><th>PBR</th><th>ROE%</th></tr></thead>
<tbody>{top_rows}</tbody></table></div>

<p class="muted" style="margin-top:16px">
<a href="/learn/per">PER</a>·<a href="/learn/pbr">PBR</a>·<a href="/learn/roe">ROE</a>
용어가 익숙하지 않다면 용어해설을 참고하세요.
<a href="/sector-report">← 업종별 리포트 전체</a></p>
"""
    desc = f"{sector_name} 업종의 평균 PER·PBR·ROE·부채비율과 저평가·우량 종목 TOP10 밸류에이션 분석."
    return layout(f"{sector_name} 업종 밸류에이션 리포트 — 저평가·우량 종목 분석",
                  desc, canonical, body)


def render_sector_index(canonical):
    items = "".join(
        f'<li><a href="/sector-report/{_esc(slug)}">{_esc(name)}</a></li>'
        for name, slug in SLUGS.items())
    body = (f'<h1>📊 업종별 밸류에이션 리포트</h1>'
            f'<p class="muted">각 업종의 평균 PER·PBR·ROE·부채비율과 저평가·우량 종목을 정리했습니다. '
            f'테마(모멘텀) 페이지와 달리 밸류에이션 관점입니다.</p>'
            f'<ul style="line-height:2.2;font-size:14.5px">{items}</ul>')
    return layout("업종별 밸류에이션 리포트 전체 — 저평가·우량 종목 분석",
                  "반도체·2차전지·바이오 등 16개 업종의 평균 밸류에이션과 저평가·우량 종목을 "
                  "정리한 업종별 리포트 목록.", canonical, body)
