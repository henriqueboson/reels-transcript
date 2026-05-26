@echo off
REM Transcritor de Reels - inicializador para Windows.
REM Cria/ativa a .venv, instala dependencias, atualiza o yt-dlp e roda o app.

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py"
) else (
    set "PY=python"
)

if not exist ".venv" (
    echo Criando ambiente virtual...
    %PY% -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo Instalando dependencias...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo Atualizando yt-dlp...
python -m pip install --upgrade yt-dlp

echo Iniciando o app...
python app.py

pause
