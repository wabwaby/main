@echo off
setlocal

cd /d "%~dp0\.."

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 project-atrocities\build_exe.py
) else (
    python project-atrocities\build_exe.py
)

echo.
pause
