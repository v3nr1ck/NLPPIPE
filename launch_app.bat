@echo off
setlocal

echo.
echo  CMMS NLP Pipeline -- FastAPI Web App
echo =======================================

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python not found. Install from https://python.org
    pause & exit /b 1
)

:: Create venv if needed
if not exist "venv\" (
    echo  Creating virtual environment...
    python -m venv venv
)

:: Activate and install deps
call venv\Scripts\activate.bat
echo  Installing / verifying dependencies...
pip install -q -r requirements.txt

:: Open browser after a short delay
start "" /b cmd /c "timeout /t 3 >nul && start http://localhost:8000"

echo.
echo  Starting server at http://localhost:8000
echo  Press Ctrl+C to stop.
echo.

uvicorn app:app --host 0.0.0.0 --port 8000 --reload

pause
