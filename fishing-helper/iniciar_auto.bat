@echo off
cd /d "%~dp0"
if not exist ".venv-auto\Scripts\python.exe" (
    echo Ambiente .venv-auto nao encontrado. Consulte o README.
    pause
    exit /b 1
)
".venv-auto\Scripts\python.exe" fishing_auto.py --auto-start
if errorlevel 1 pause
