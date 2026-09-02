# =====================================================================
#  Local content self-heal - run by Windows Task Scheduler several times
#  each morning. Supersedes sync_content.bat: it (1) pulls remote content,
#  (2) restores locally-missing tracked files, and crucially (3) FORCE-
#  TRIGGERS the GitHub content workflow if today's content is still missing.
#
#  Why: GitHub Actions schedule(cron) events get dropped en masse on high-
#  load days (happened 2026-08-07/27/28 - primary + cron backstops all
#  missed together). Adding more GitHub cron backstops is useless - they
#  drop together. Instead the reliable LOCAL scheduler force-generates via
#  workflow_dispatch, which (unlike schedule events) is not dropped by load.
#
#  Triggers at most once per day (marker file) so on non-content days
#  (market holidays) it doesn't re-trigger every slot - that day's workflow
#  no-ops via daily_content.py's own logic. Sunday is skipped outright.
#  ASCII-only on purpose: PowerShell 5.1 reads .ps1 as cp949, so Korean
#  text here would be mangled into parse errors.
#  Log: content_sync.log
# =====================================================================
$ErrorActionPreference = 'SilentlyContinue'
# Build path from $env:USERPROFILE at runtime so the Korean username never
# appears as literal text in this .ps1 (PS 5.1 reads .ps1 as cp949; literal
# Korean here would be mangled and break Set-Location/paths silently).
$proj = Join-Path $env:USERPROFILE 'Desktop\STOCK_PROJECT\kr_screener'
Set-Location $proj
$log = Join-Path $proj 'content_sync.log'
function Log($m) { Add-Content -Path $log -Value ("[{0}] {1}" -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $m) -Encoding utf8 }

Log 'ensure_content: pull start'
git pull *>> $log

# us_screener(미국) 레포도 아침에 로컬로 당겨온다 — 한국어 미국 브리핑(kr_briefing.txt)·
# 카드가 그 레포 content_out에 쌓이므로, 네이버에 붙일 수 있게 로컬로 내려받는다.
$us = Join-Path $env:USERPROFILE 'Desktop\STOCK_PROJECT\us_screener'
if (Test-Path $us) {
    Log 'ensure_content: us_screener pull'
    git -C $us pull *>> $log
}

# Integrity: a clean pull once left tracked files locally missing
# (2026-07-27, antivirus/indexer lock suspected). If content_out shows
# deletions (' D '), restore them.
$missing = (git status --porcelain content_out) | Where-Object { $_ -match '^ D ' }
if ($missing) {
    Log 'ensure_content: WARNING local files missing after pull - restoring'
    git checkout -- content_out *>> $log
}

# Check today's content (machine TZ = KST). If absent, force-trigger workflow.
$today = (Get-Date).ToString('yyyy-MM-dd')
$draft = Join-Path $proj "content_out\$today\blog_draft.txt"
$marker = Join-Path $env:LOCALAPPDATA "moneycheckup_content_triggered_$today.flag"

if ((Get-Date).DayOfWeek -eq 'Sunday') {
    Log "ensure_content: Sunday - no content day, skip"
}
elseif (Test-Path $draft) {
    Log "ensure_content: today ($today) content present - OK"
}
elseif (Test-Path $marker) {
    Log "ensure_content: today ($today) still missing but already triggered - waiting (next slot pulls)"
}
else {
    Log "ensure_content: today ($today) content missing - force-triggering daily-content.yml"
    & 'C:\Program Files\GitHub CLI\gh.exe' workflow run daily-content.yml *>> $log
    if ($?) { New-Item -ItemType File -Path $marker -Force | Out-Null; Log 'ensure_content: trigger OK, marker created' }
    else { Log 'ensure_content: trigger FAILED (gh) - will retry next slot' }
}

# AI 배경 카드(ai-cards.yml)도 스케줄 드롭 대비 로컬에서 보장 — 오늘 후보 폴더가
# 없으면 워크플로우를 강제 트리거(하루 1회). content와 별개 마커 사용.
$cards = Join-Path $proj "content_out\$today\ai_card_candidates\cover.png"
$cmark = Join-Path $env:LOCALAPPDATA "moneycheckup_cards_triggered_$today.flag"
if ((Get-Date).DayOfWeek -eq 'Sunday') {
    # 일요일은 카드도 스킵
}
elseif (Test-Path $cards) {
    Log "ensure_content: today ($today) AI cards present - OK"
}
elseif (-not (Test-Path $cmark)) {
    Log "ensure_content: today ($today) AI cards missing - force-triggering ai-cards.yml"
    & 'C:\Program Files\GitHub CLI\gh.exe' workflow run ai-cards.yml *>> $log
    if ($?) { New-Item -ItemType File -Path $cmark -Force | Out-Null }
}

# ============ us_screener (US market) morning pipeline force-trigger ============
# GitHub schedule events run 2-8h late on us_screener too (prices "06:00" often
# actually starts 08-14h; fundamentals takes ~33min). workflow_dispatch is not
# dropped, so we force the chain locally to land the US briefing before 07:30 KST:
#   1) prices + fundamentals first,
#   2) after >=40min (fundamentals ~33min) the KR-format briefing, so its
#      going-concern list uses same-day audit data.
# Only KST Tue-Sat (mornings after a US regular session; Sun/Mon = US closed).
# Gated to >=06:00 KST (=21:00 UTC) so prices run after the US close under both
# EST and EDT. The top-of-script 'git -C $us pull' then downloads the result on a
# later slot. Two independent once-per-day markers stage the two steps.
$usDow = (Get-Date).DayOfWeek
if ($usDow -ne 'Sunday' -and $usDow -ne 'Monday' -and (Get-Date).Hour -ge 6) {
    $ghExe = 'C:\Program Files\GitHub CLI\gh.exe'
    $usToday = (Get-Date).ToString('yyyy-MM-dd')
    $usDataMark = Join-Path $env:LOCALAPPDATA "mn_scan_data_triggered_$usToday.flag"
    $usInsMark = Join-Path $env:LOCALAPPDATA "mn_scan_insight_triggered_$usToday.flag"
    if (-not (Test-Path $usDataMark)) {
        Log 'ensure_content: US prices+fundamentals force-trigger'
        & $ghExe workflow run daily-prices.yml -R jglee92/MN_SCAN *>> $log
        & $ghExe workflow run daily-fundamentals.yml -R jglee92/MN_SCAN *>> $log
        New-Item -ItemType File -Path $usDataMark -Force | Out-Null
    }
    elseif (-not (Test-Path $usInsMark)) {
        $usAge = (New-TimeSpan -Start (Get-Item $usDataMark).LastWriteTime -End (Get-Date)).TotalMinutes
        if ($usAge -ge 40) {
            Log ('ensure_content: US briefing force-trigger (data +{0}min)' -f [int]$usAge)
            & $ghExe workflow run daily-insight.yml -R jglee92/MN_SCAN *>> $log
            New-Item -ItemType File -Path $usInsMark -Force | Out-Null
        }
        else {
            Log ('ensure_content: US briefing waiting (data +{0}min, need 40)' -f [int]$usAge)
        }
    }
    else {
        Log 'ensure_content: US pipeline already triggered today - OK'
    }
}
Log 'ensure_content: done'
