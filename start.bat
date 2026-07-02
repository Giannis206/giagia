@echo off
cd /d C:\giagia
call .venv\Scripts\activate.bat

REM Έλεγχος αν ο server τρέχει ήδη
curl -s http://localhost:5000/health >nul 2>&1
if %errorlevel%==0 (
    start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" "http://localhost:5000"
    exit /b
)

REM Εκκίνηση server στο background
start /min cmd /c "call C:\giagia\.venv\Scripts\activate.bat && python C:\giagia\app.py"

REM Αναμονή μέχρι να εκκινήσει
:wait
timeout /t 1 /nobreak >nul
curl -s http://localhost:5000/health >nul 2>&1
if not %errorlevel%==0 goto wait

REM Άνοιγμα Edge
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" "http://localhost:5000"
