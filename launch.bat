@echo off
title CUA-Sentinel Launcher
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0scripts\launcher.py"
) else (
    python "%~dp0scripts\launcher.py"
)

if errorlevel 1 (
    echo.
    echo [!] Launcher exited with error. Press any key to close.
    pause >nul
)