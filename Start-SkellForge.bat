@echo off
setlocal
cd /d "%~dp0"
title SkellForge Studio
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m skellforge studio
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python 3.10+ not found. Install Python and enable it in PATH.
        pause
        exit /b 1
    )
    python -m skellforge studio
)
if errorlevel 1 (
    echo.
    echo SkellForge exited with an error. Check dependencies with:
    echo python -m skellforge doctor
    pause
)
