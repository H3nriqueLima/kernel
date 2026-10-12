@echo off
rem Liga o K.E.R.N.E.L em segundo plano (sem janela de console) e abre o chat.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Ambiente nao encontrado. Rode primeiro: powershell -ExecutionPolicy Bypass -File instalar.ps1
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m kernel iniciar --janela
