# 매일 자동 갱신 (Windows 작업 스케줄러에서 호출)
# - 서버가 꺼져있으면 기동(0.0.0.0:8010) → 가격 증분 → 재무/배당 보충(없는 것만) → 캐시 새로고침
$ErrorActionPreference = 'SilentlyContinue'
$proj = 'c:\Users\이종근\Desktop\STOCK_PROJECT\kr_screener'
$py = Join-Path $proj '.venv\Scripts\python.exe'
Set-Location $proj
$env:PYTHONIOENCODING = 'utf-8'

# 1) 서버 살아있나 확인, 없으면 백그라운드 기동
$up = $false
try { $r = Invoke-WebRequest 'http://127.0.0.1:8010/api/backtest' -TimeoutSec 5; if ($r.StatusCode -eq 200) { $up = $true } } catch {}
if (-not $up) {
    Start-Process -WindowStyle Hidden -FilePath $py `
        -ArgumentList '-m', 'uvicorn', 'app:app', '--host', '0.0.0.0', '--port', '8010'
    Start-Sleep -Seconds 10
}

# 2) 가격 증분 갱신
& $py update_data.py

# 3) 재무/배당 보충 (이미 있는 연도는 스킵 → 평소엔 거의 즉시)
& $py refresh_fundamentals.py

# 4) 대시보드 랭킹/섹터 캐시 재계산
try { Invoke-RestMethod -Method Post 'http://127.0.0.1:8010/api/refresh' -TimeoutSec 180 | Out-Null } catch {}

Write-Output ("[{0}] daily_update 완료" -f (Get-Date))
