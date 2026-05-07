@echo off
setlocal

cd /d "%~dp0\.."

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 love-letter\build_exe.py
) else (
    python love-letter\build_exe.py
)

echo.
pause
