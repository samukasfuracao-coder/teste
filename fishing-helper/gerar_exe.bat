@echo off
cd /d "%~dp0"
if not exist ".venv-auto\Scripts\python.exe" (
    echo Ambiente .venv-auto nao encontrado. Consulte o README.
    pause
    exit /b 1
)
".venv-auto\Scripts\python.exe" -m pip install "pyinstaller>=6,<7"
if errorlevel 1 goto failed
set "PESCA_ICON_ARGS="
if exist "icone.ico" set PESCA_ICON_ARGS=--icon "icone.ico" --add-data "icone.ico;."
".venv-auto\Scripts\python.exe" -m PyInstaller --noconfirm --onedir --windowed --name PescaAuto %PESCA_ICON_ARGS% --collect-all rapidocr_onnxruntime --collect-all onnxruntime --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 fishing_auto.py
if errorlevel 1 goto failed
echo Pronto: dist\PescaAuto\PescaAuto.exe
echo Mantenha o EXE junto com todos os arquivos da pasta PescaAuto.
pause
exit /b 0
:failed
echo Falha ao gerar executavel. Copie a mensagem de erro.
pause
exit /b 1
