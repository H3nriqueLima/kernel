@echo off
rem O freio de mao: para o servico inteiro, mesmo sem a janela de chat aberta.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m kernel desligar
pause
