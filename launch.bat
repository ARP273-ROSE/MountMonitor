@echo off
REM MountMonitor Launcher for Windows
REM Detects Python, creates venv if needed, installs dependencies, and launches

echo MountMonitor - Telescope Mount Monitor
echo ========================================

REM Check for Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found in PATH
    echo Please install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

REM Check Python version
python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'" 2>nul
if %ERRORLEVEL% neq 0 (
    echo WARNING: Python 3.11+ recommended. Trying with current version...
)

REM Create venv if not exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install/update dependencies
pip install -q -r requirements.txt 2>nul

REM Parse arguments
set SIM_ARG=
if "%1"=="simAll" set SIM_ARG=--sim-all
if "%1"=="simMount" set SIM_ARG=--sim-mount
if "%1"=="simSeismometer" set SIM_ARG=--sim-seismometer

REM Launch
echo Starting MountMonitor...
python main.py %SIM_ARG%

REM Deactivate
deactivate
