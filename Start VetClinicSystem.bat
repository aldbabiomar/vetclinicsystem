@echo off
REM VetClinicSystem — double-click launcher (Windows)
REM First run: creates a virtual environment, installs dependencies, sets up
REM PostgreSQL in Docker, and loads your data. Every run after that: just
REM starts the app and opens it in your browser.

cd /d "%~dp0"

echo VetClinicSystem - starting up...
echo.

REM 1. Create the virtual environment if it doesn't exist yet
if not exist "venv\" (
    echo First-time setup: creating a Python environment for the app...
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo Could not create the environment. Make sure Python 3 is installed
        echo and added to PATH ^(python --version in Command Prompt should show
        echo a version number^).
        pause
        exit /b 1
    )
)

REM 2. Activate it
call venv\Scripts\activate.bat

REM 3. Install dependencies if they're not already there
python -c "import flask, reportlab, PIL, psycopg, waitress, apscheduler, dotenv" 2>nul
if errorlevel 1 (
    echo First-time setup: installing dependencies...
    python -m pip install --quiet -r requirements.txt
)

REM 4. Set up PostgreSQL (Docker), schema, and data — every run; each step
REM    skips itself automatically once it's already done.
python setup.py
if errorlevel 1 (
    echo.
    echo Setup did not finish.
    pause
    exit /b 1
)

REM 5. setup.py puts a new install on the update-ready layout: from now on the
REM    app runs from ..\vetclinicsystem-data, through the launcher there, which
REM    also picks up updates. Hand over to it.
if exist "..\vetclinicsystem-data\Start VetClinicSystem.bat" (
    call venv\Scripts\deactivate.bat
    call "..\vetclinicsystem-data\Start VetClinicSystem.bat"
    exit /b
)

REM 6. A checkout set up with --no-enable-updates runs here, on its .env's port.
if not defined VETCLINICSYSTEM_PORT if exist ".env" for /f "usebackq tokens=1,* delims==" %%A in (".env") do if "%%A"=="VETCLINICSYSTEM_PORT" set "VETCLINICSYSTEM_PORT=%%B"
if not defined VETCLINICSYSTEM_PORT set "VETCLINICSYSTEM_PORT=5050"
start "" cmd /c "timeout /t 2 >nul && start http://127.0.0.1:%VETCLINICSYSTEM_PORT%"

echo.
echo VetClinicSystem is running at http://127.0.0.1:%VETCLINICSYSTEM_PORT%
echo Leave this window open while you use the app.
echo Close this window ^(or press Ctrl+C^) to stop it.
echo.

python run.py
