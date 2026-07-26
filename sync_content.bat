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

rem ---------------------------------------------------------------------
rem Integrity check: a clean pull should never leave tracked files
rem locally missing. This happened once (2026-07-27, 4 card PNGs vanished
rem from the working copy even though the pull itself only touched
rem unrelated files per its own diffstat) - exact cause unconfirmed
rem (antivirus/indexer lock on this PC is the leading guess), so this
rem auto-heals it and logs it instead of leaving stale/missing files
rem sitting there until someone happens to notice.
rem ---------------------------------------------------------------------
git status --porcelain content_out\ | findstr /c:" D " > nul
if not errorlevel 1 (
  echo [%date% %time%] WARNING: local files missing after pull - restoring >> content_sync.log
  git status --porcelain content_out\ >> content_sync.log
  git checkout -- content_out\
  echo [%date% %time%] restore done >> content_sync.log
)
