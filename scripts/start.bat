@echo off
REM Startup script for local development on Windows

echo Starting Acme Product Importer...

REM Check if .env exists
if not exist .env (
    echo Warning: .env file not found. Creating from .env.example...
    if exist .env.example (
        copy .env.example .env
        echo Please update .env with your database and Redis credentials.
    ) else (
        echo Error: .env.example not found. Please create .env manually.
        exit /b 1
    )
)

REM Check if virtual environment exists
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install -r backend\requirements.txt

REM Run database migrations (if Alembic is set up)
if exist backend\alembic (
    echo Running database migrations...
    cd backend
    alembic upgrade head
    cd ..
)

echo.
echo Setup complete!
echo.
echo To start the application:
echo   Terminal 1 (API): uvicorn backend.app.main:app --reload --port 8000
echo   Terminal 2 (Worker): dramatiq backend.app.tasks --processes 1 --threads 4
echo.
echo Then open http://localhost:8000 in your browser.

