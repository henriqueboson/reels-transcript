"""Transcritor de Reels — app web local.

Baixa o áudio de reels do Instagram com yt-dlp e transcreve usando a API da
OpenAI (modelo gpt-4o-mini-transcribe). Interface Flask no navegador: cole os
links (um por linha), clique em Transcrever e os resultados aparecem um a um.
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import webbrowser

from dotenv import load_dotenv
from flask import Flask, Response, render_template_string, request, stream_with_context
from openai import OpenAI
from yt_dlp import YoutubeDL

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
COOKIES_FROM_BROWSER = os.getenv("COOKIES_FROM_BROWSER", "").strip()

# Modelo de transcrição da OpenAI.
TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"

# Quando COOKIES_FROM_BROWSER está vazio: tenta primeiro sem login e, se falhar,
# tenta importar cookies de cada navegador automaticamente.
DEFAULT_BROWSER_ATTEMPTS = [None, "chrome", "firefox", "safari", "edge"]

app = Flask(__name__)


def _browser_attempts():
    """Lista de navegadores (ou None) a tentar para baixar o áudio."""
    if COOKIES_FROM_BROWSER:
        return [COOKIES_FROM_BROWSER]
    return DEFAULT_BROWSER_ATTEMPTS


def download_audio(url, tmpdir):
    """Baixa o melhor áudio do reel em ``tmpdir`` e devolve o caminho do arquivo.

    Usa ``bestaudio`` sem pós-processamento, então não depende de um ffmpeg
    instalado no sistema. Tenta os navegadores configurados em sequência.
    """
    base_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nopart": True,
    }

    # primary_err guarda o erro da tentativa sem login, que costuma ser o motivo
    # real (ex.: link inexistente / pede login). last_err é o fallback.
    primary_err = None
    last_err = None
    for browser in _browser_attempts():
        # Limpa tentativas anteriores para não pegar um arquivo parcial.
        for leftover in os.listdir(tmpdir):
            try:
                os.remove(os.path.join(tmpdir, leftover))
            except OSError:
                pass

        opts = dict(base_opts)
        if browser:
            opts["cookiesfrombrowser"] = (browser,)

        try:
            with YoutubeDL(opts) as ydl:
                ydl.extract_info(url, download=True)
            files = [
                os.path.join(tmpdir, f)
                for f in os.listdir(tmpdir)
                if os.path.isfile(os.path.join(tmpdir, f))
            ]
            if files:
                return max(files, key=os.path.getsize)
            last_err = RuntimeError("download concluído mas nenhum arquivo de áudio foi encontrado")
        except Exception as exc:  # noqa: BLE001 - queremos seguir para o próximo navegador
            # "cookies database" = o navegador simplesmente não está instalado /
            # sem cookies; não é um erro real de download, então não sobrescreve.
            if "cookies database" in str(exc).lower():
                continue
            if browser is None:
                primary_err = exc
            last_err = exc

    raise RuntimeError(_clean_error(primary_err or last_err))


def transcribe_audio(audio_path, client):
    """Envia o arquivo de áudio para a OpenAI e devolve o texto transcrito."""
    with open(audio_path, "rb") as audio_file:
        result = client.audio.transcriptions.create(
            model=TRANSCRIBE_MODEL,
            file=audio_file,
        )
    return result.text.strip()


def process_link(url, client):
    """Baixa e transcreve um único link. Levanta exceção em caso de erro."""
    with tempfile.TemporaryDirectory(prefix="reel_") as tmpdir:
        audio_path = download_audio(url, tmpdir)
        return transcribe_audio(audio_path, client)


def _clean_error(err):
    """Resume mensagens de erro longas (yt-dlp costuma ser verboso)."""
    msg = str(err) if err else "erro desconhecido"
    msg = msg.replace("\n", " ").strip()
    low = msg.lower()
    if any(s in low for s in (
        "empty media response", "cookies-from-browser", "sign in to confirm",
        "login required", "rate-limit", "rate limit", "requested content is not available",
    )):
        return (
            "O Instagram não liberou este link sem login (pode ser privado, inexistente "
            "ou estar pedindo autenticação). Se o post abre no seu navegador, defina "
            "COOKIES_FROM_BROWSER no .env (ex.: chrome) e tente de novo."
        )
    if len(msg) > 300:
        msg = msg[:300] + "…"
    return msg


PAGE = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transcritor de Reels</title>
<style>
  :root {
    --bg: #0f1117; --card: #1a1d27; --border: #2a2e3c; --text: #e7e9ee;
    --muted: #9aa0ad; --accent: #7c5cff; --accent-2: #5b8def;
    --ok: #36d399; --err: #f87272;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    line-height: 1.5;
  }
  .wrap { max-width: 820px; margin: 0 auto; padding: 40px 20px 80px; }
  header h1 { margin: 0 0 6px; font-size: 26px; letter-spacing: -.4px; }
  header p { margin: 0 0 28px; color: var(--muted); }
  .badge {
    display: inline-block; background: linear-gradient(135deg, var(--accent), var(--accent-2));
    width: 44px; height: 44px; border-radius: 12px; margin-bottom: 16px;
    text-align: center; line-height: 44px; font-size: 22px;
  }
  textarea {
    width: 100%; min-height: 130px; resize: vertical; padding: 14px 16px;
    background: var(--card); color: var(--text); border: 1px solid var(--border);
    border-radius: 12px; font-size: 14px; font-family: inherit;
  }
  textarea:focus { outline: none; border-color: var(--accent); }
  .row { display: flex; align-items: center; gap: 14px; margin-top: 14px; }
  button {
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: #fff; border: 0; padding: 12px 24px; border-radius: 10px;
    font-size: 15px; font-weight: 600; cursor: pointer;
  }
  button:disabled { opacity: .5; cursor: not-allowed; }
  .hint { color: var(--muted); font-size: 13px; }
  #results { margin-top: 32px; display: flex; flex-direction: column; gap: 14px; }
  .card {
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px 18px;
  }
  .card .url { font-size: 12px; color: var(--muted); word-break: break-all; margin-bottom: 8px; }
  .card .status { font-size: 13px; font-weight: 600; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
  .card .text { white-space: pre-wrap; font-size: 14px; }
  .card.ok .status { color: var(--ok); }
  .card.error .status { color: var(--err); }
  .card.pending .status { color: var(--accent-2); }
  .spinner {
    width: 14px; height: 14px; border: 2px solid var(--border);
    border-top-color: var(--accent-2); border-radius: 50%;
    animation: spin .7s linear infinite; display: inline-block;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .copy {
    background: none; border: 1px solid var(--border); color: var(--muted);
    padding: 4px 10px; font-size: 12px; font-weight: 500; border-radius: 7px;
    float: right; margin-top: -2px;
  }
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="badge">🎬</div>
      <h1>Transcritor de Reels</h1>
      <p>Cole os links dos reels (um por linha) e clique em Transcrever.</p>
    </header>

    <textarea id="links" placeholder="https://www.instagram.com/reel/...
https://www.instagram.com/reel/...
https://www.instagram.com/reel/..."></textarea>

    <div class="row">
      <button id="go">Transcrever</button>
      <span class="hint" id="hint">Processa um link de cada vez.</span>
    </div>

    <div class="row" id="bulkRow" style="display:none">
      <button id="copyAll" class="copy">Copiar todas</button>
    </div>

    <div id="results"></div>
  </div>

<script>
const go = document.getElementById('go');
const linksEl = document.getElementById('links');
const resultsEl = document.getElementById('results');
const hintEl = document.getElementById('hint');
const bulkRow = document.getElementById('bulkRow');
const copyAll = document.getElementById('copyAll');

function cardId(i) { return 'card-' + i; }

copyAll.addEventListener('click', () => {
  const blocks = [...document.querySelectorAll('.card.ok')].map(c => {
    const url = (c.querySelector('.url') || {}).textContent || '';
    const txt = (c.querySelector('.text') || {}).textContent || '';
    return url + '\\n' + txt;
  });
  if (!blocks.length) return;
  navigator.clipboard.writeText(blocks.join('\\n\\n----------\\n\\n'));
  copyAll.textContent = 'Copiado!';
  setTimeout(() => { copyAll.textContent = 'Copiar todas'; }, 1500);
});

function renderPending(links) {
  resultsEl.innerHTML = '';
  bulkRow.style.display = 'none';
  links.forEach((url, i) => {
    const div = document.createElement('div');
    div.className = 'card pending';
    div.id = cardId(i);
    div.innerHTML = `
      <div class="url">${escapeHtml(url)}</div>
      <div class="status"><span class="spinner"></span> Na fila…</div>`;
    resultsEl.appendChild(div);
  });
}

function updateCard(r) {
  const div = document.getElementById(cardId(r.index));
  if (!div) return;
  if (r.status === 'ok') {
    div.className = 'card ok';
    div.innerHTML = `
      <button class="copy">Copiar</button>
      <div class="url">${escapeHtml(r.url)}</div>
      <div class="status">✓ Transcrito</div>
      <div class="text">${escapeHtml(r.text || '(vazio)')}</div>`;
    div.querySelector('.copy').addEventListener('click', () => {
      navigator.clipboard.writeText(r.text || '');
      div.querySelector('.copy').textContent = 'Copiado!';
    });
    bulkRow.style.display = 'flex';
  } else {
    div.className = 'card error';
    div.innerHTML = `
      <div class="url">${escapeHtml(r.url)}</div>
      <div class="status">✕ Erro</div>
      <div class="text">${escapeHtml(r.error || 'falha desconhecida')}</div>`;
  }
}

function markProcessing(i) {
  const div = document.getElementById(cardId(i));
  if (div) div.querySelector('.status').innerHTML = '<span class="spinner"></span> Transcrevendo…';
}

function escapeHtml(s) {
  return (s || '').replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

go.addEventListener('click', async () => {
  const links = linksEl.value.split('\\n').map(s => s.trim()).filter(Boolean);
  if (!links.length) { hintEl.textContent = 'Cole pelo menos um link.'; return; }

  go.disabled = true;
  hintEl.textContent = 'Processando ' + links.length + ' link(s)…';
  renderPending(links);
  if (links.length) markProcessing(0);

  try {
    const resp = await fetch('/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ links })
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let done = 0;
    while (true) {
      const { value, done: streamDone } = await reader.read();
      if (streamDone) break;
      buffer += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buffer.indexOf('\\n')) >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (!line) continue;
        const r = JSON.parse(line);
        updateCard(r);
        done++;
        if (done < links.length) markProcessing(done);
      }
    }
    hintEl.textContent = 'Concluído.';
  } catch (e) {
    hintEl.textContent = 'Erro de conexão: ' + e.message;
  } finally {
    go.disabled = false;
  }
});
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/transcribe", methods=["POST"])
def transcribe():
    if not OPENAI_API_KEY:
        return Response(
            json.dumps({"index": 0, "url": "", "status": "error",
                        "error": "OPENAI_API_KEY não configurada no .env"}) + "\n",
            mimetype="application/x-ndjson",
        )

    data = request.get_json(silent=True) or {}
    links = [str(l).strip() for l in data.get("links", []) if str(l).strip()]
    client = OpenAI(api_key=OPENAI_API_KEY)

    def generate():
        for i, url in enumerate(links):
            result = {"index": i, "url": url}
            try:
                result["text"] = process_link(url, client)
                result["status"] = "ok"
            except Exception as exc:  # noqa: BLE001 - um link com erro não para os demais
                result["status"] = "error"
                result["error"] = _clean_error(exc)
            yield json.dumps(result, ensure_ascii=False) + "\n"

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")


def open_browser():
    webbrowser.open("http://localhost:5000")


APP_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(APP_DIR, ".env")
ENV_EXAMPLE_PATH = os.path.join(APP_DIR, ".env.example")


def _write_api_key(key):
    """Grava/atualiza a linha OPENAI_API_KEY no .env preservando o resto."""
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    out, found = [], False
    for line in lines:
        if line.startswith("OPENAI_API_KEY="):
            out.append("OPENAI_API_KEY=" + key)
            found = True
        else:
            out.append(line)
    if not found:
        out.append("OPENAI_API_KEY=" + key)
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def ensure_env_file():
    """Garante um .env com a chave preenchida; pede a chave no terminal se faltar.

    Resolve o atrito do macOS: o usuário não precisa achar/renomear o arquivo
    oculto .env.example — o app cria o .env e coleta a chave na primeira vez.
    """
    if not os.path.exists(ENV_PATH):
        if os.path.exists(ENV_EXAMPLE_PATH):
            shutil.copyfile(ENV_EXAMPLE_PATH, ENV_PATH)
        else:
            with open(ENV_PATH, "w", encoding="utf-8") as f:
                f.write("OPENAI_API_KEY=\nCOOKIES_FROM_BROWSER=\n")

    if OPENAI_API_KEY:
        return

    # Só dá para perguntar se há um terminal interativo. Em execução sem
    # terminal, segue em frente (a interface mostra o erro de chave ausente).
    if not (sys.stdin and sys.stdin.isatty()):
        return

    print("")
    print("=== Configuração inicial ===")
    print("Cole sua chave da OpenAI (começa com sk-...) e tecle Enter:")
    try:
        key = input("> ").strip()
    except EOFError:
        key = ""
    if key:
        _write_api_key(key)
        # Atualiza para este processo (a interface usa estas variáveis globais).
        globals()["OPENAI_API_KEY"] = key
        print("Chave salva no arquivo .env.\n")
    else:
        print("Nenhuma chave informada — você pode colá-la depois no arquivo .env.\n")


if __name__ == "__main__":
    # No console legado do Windows (cp1252/cp850), caracteres fora da codificação
    # quebrariam os prints; tolera-os em vez de derrubar o app.
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ensure_env_file()
    # Abre o navegador automaticamente assim que o servidor sobe.
    threading.Timer(1.2, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
