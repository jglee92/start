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
Log 'ensure_content: done'
