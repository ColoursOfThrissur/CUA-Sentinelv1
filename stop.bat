@echo off
title Stop CUA-Sentinel
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0scripts\stop_services.py" %*
) else (
    python "%~dp0scripts\stop_services.py" %*
)

ping 127.0.0.1 -n 3 >nul