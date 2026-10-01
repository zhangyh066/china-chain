@echo off
cd /d "%~dp0"
echo.
echo   China Supply Chain Atlas  --  local preview
echo   ------------------------------------------------
echo   Open in browser:  http://127.0.0.1:8123/
echo   Stop:             press Ctrl+C, or close this window
echo.
echo   Keep this window open while you browse the site.
echo.
where py >nul 2>nul
if %errorlevel%==0 (
  py serve.py 8123
) else (
  python serve.py 8123
)
if errorlevel 1 (
  echo.
  echo   Python not found. Install Python 3, then run this again.
  pause
)
