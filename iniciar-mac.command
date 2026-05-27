#!/bin/bash
# Transcritor de Reels - inicializador para macOS.
# Cria/ativa a .venv, instala dependencias, atualiza o yt-dlp e roda o app.

cd "$(dirname "$0")" || exit 1

# Remove a marca de "quarentena" do Gatekeeper dos arquivos da pasta, para que
# nas proximas vezes o app abra sem o aviso "a Apple nao pode verificar...".
xattr -dr com.apple.quarantine . >/dev/null 2>&1

if command -v python3 >/dev/null 2>&1; then
    PY=python3
else
    PY=python
fi

if [ ! -d ".venv" ]; then
    echo "Criando ambiente virtual..."
    "$PY" -m venv .venv
fi

source .venv/bin/activate

echo "Instalando dependencias..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "Atualizando yt-dlp..."
python -m pip install --upgrade yt-dlp

echo "Iniciando o app..."
python app.py
