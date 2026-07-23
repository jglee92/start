@echo off
rem =====================================================================
rem  Morning content sync - run by Windows Task Scheduler every morning.
rem  Pulls today's blog draft + instagram cards (generated and committed
rem  by GitHub Actions daily-content.yml) into this PC's content_out folder.
rem  Without this, the local folder stays stale because nothing on this PC
rem  auto-pulls (that was the real cause of "files not showing up daily").
rem  Double-click also works for a manual run. Log: content_sync.log
rem  (ASCII-only on purpose: cmd reads .bat as cp949, so Korean text here
rem   would be mangled and misread as commands.)
rem =====================================================================
cd /d "%~dp0"
echo.>> content_sync.log
echo [%date% %time%] pull start >> content_sync.log
git pull >> content_sync.log 2>&1
if errorlevel 1 (
  echo [%date% %time%] pull FAILED - check log >> content_sync.log
) else (
  echo [%date% %time%] pull done >> content_sync.log
)
