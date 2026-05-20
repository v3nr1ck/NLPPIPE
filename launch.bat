@echo off
:: =============================================================================
::  CMMS NLP Pipeline — Windows Launcher
::  Double-click this file to launch the interactive demo.
::  First run: sets up Python venv + installs dependencies (~30 seconds)
::  Subsequent runs: instant
:: =============================================================================
title CMMS NLP Pipeline — Setup & Launch
cd /d "%~dp0"

echo.
echo   🐶 CMMS NLP Pipeline — v1.1.0
echo   ========================================
echo.

:: ── Check Python ──────────────────────────────────────────────────
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   [ERROR] Python not found!
    echo.
    echo   Please install Python 3.10+ from https://python.org
    echo   Make sure to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

python --version
echo.

:: ── Create venv if needed ─────────────────────────────────────────
if not exist "venv\" (
    echo   [1/3] Creating virtual environment...
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo   [ERROR] Failed to create venv. Check Python install.
        pause
        exit /b 1
    )
) else (
    echo   [1/3] Virtual environment found ^(skip^)
)

:: ── Install deps ──────────────────────────────────────────────────
echo   [2/3] Installing dependencies...
call venv\Scripts\activate.bat
pip install -q pydantic streamlit
if %ERRORLEVEL% NEQ 0 (
    echo   [ERROR] pip install failed. Check internet connection.
    pause
    exit /b 1
)

:: ── Launch ────────────────────────────────────────────────────────
echo   [3/3] Launching dashboard...
echo.
echo   ╔══════════════════════════════════════════════════╗
echo   ║  Opening http://localhost:8501 in your browser  ║
echo   ║  Press Ctrl+C here to stop the server          ║
echo   ╚══════════════════════════════════════════════════╝
echo.
timeout /t 2 /nobreak >nul
start "" http://localhost:8501
streamlit run dashboard.py --server.headless true

pause
