@echo off
title CUA-Sentinel
setlocal

set ROOT=%~dp0

:: ── 1. Build frontend ──────────────────────────────────────────
echo [1/3] Building frontend...
cd /d "%ROOT%frontend"
call npm install -q
call npm run build
if errorlevel 1 (
    echo ERROR: Frontend build failed.
    pause & exit /b 1
)

:: ── 2. Start backend ───────────────────────────────────────────
echo [2/3] Starting backend...
cd /d "%ROOT%backend"

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -r requirements.txt -q

start "CUA-Sentinel Backend" cmd /k "call .venv\Scripts\activate.bat && python main.py"

:: Give backend a moment to start
timeout /t 3 /nobreak >nul

:: ── 3. Start Cloudflare Tunnel ─────────────────────────────────
echo [3/3] Starting Cloudflare Tunnel...
echo.
echo Your public URL will appear below (look for trycloudflare.com):
echo ----------------------------------------------------------------
cloudflared tunnel --url http://localhost:8000

endlocal
