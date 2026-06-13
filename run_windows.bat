@echo off
echo.
echo  GMM Kasoa Media — Contributions System
echo  ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python is not installed or not on your PATH.
    echo  Download it from https://www.python.org/downloads/
    echo  Make sure to tick "Add Python to PATH" during install.
    pause
    exit /b 1
)

if not exist "venv\Scripts\activate.bat" (
    echo  Setting up virtual environment for the first time...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo  Installing dependencies...
    pip install -r requirements.txt --quiet
    echo  Done.
) else (
    call venv\Scripts\activate.bat
)

echo  Starting server...
echo  Open your browser and go to:  http://127.0.0.1:5000
echo  Press Ctrl+C in this window to stop the server.
echo.
python app.py
pause
