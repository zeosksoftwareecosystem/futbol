@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)
%PY% --version >nul 2>nul
if errorlevel 1 (
 echo Python tapilmadi. Python 3.10+ qurasdirin: https://www.python.org/downloads/
 pause
 exit /b 1
)
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
 echo Kitabxanalari qurasdirmaq alinmadi. Internet elaqesini yoxlayin.
 pause
 exit /b 1
)
%PY% -m streamlit run app.py
pause
