@echo off
cd /d "%~dp0backend"
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
echo Starting server at http://127.0.0.1:8008 ...
uvicorn app.main:app --host 127.0.0.1 --port 8008
