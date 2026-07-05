# 홈페이지 발행: 배포용 데이터 재생성 → GitHub push → Render 자동 재배포
#
# 사용법:
#   .\publish.ps1              → 코드/데이터 현재 상태로 발행 (슬림DB만 재생성)
#   .\publish.ps1 -RefreshData → 최신 주가·재무까지 받아서 발행 (오래 걸림)
param([switch]$RefreshData)

$ErrorActionPreference = 'Continue'
$proj = 'c:\Users\이종근\Desktop\STOCK_PROJECT\kr_screener'
$py = Join-Path $proj '.venv\Scripts\python.exe'
$env:Path += ";C:\Program Files\Git\cmd"
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $proj

if ($RefreshData) {
    Write-Host "[1/4] 최신 주가·재무 수집..." -ForegroundColor Cyan
    & $py update_data.py
    & $py refresh_fundamentals.py
} else {
    Write-Host "[1/4] 데이터 재수집 생략 (-RefreshData 주면 최신화)" -ForegroundColor DarkGray
}

Write-Host "[2/4] 배포용 슬림DB + 섹터로테이션 재생성..." -ForegroundColor Cyan
& $py build_deploy.py

Write-Host "[3/4] GitHub 커밋..." -ForegroundColor Cyan
git add -A
$msg = "update {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm')
git commit -m $msg
if ($LASTEXITCODE -ne 0) { Write-Host "  (변경사항 없음 — 발행 건너뜀)" -ForegroundColor Yellow; return }

Write-Host "[4/4] push → Render 자동 재배포..." -ForegroundColor Cyan
git push

Write-Host "`n발행 완료! 2~5분 뒤 반영 → https://kr-screener.onrender.com" -ForegroundColor Green
