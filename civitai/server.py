"""
Local web UI for civitai-bounty.

Run:  python -m civitai.server
      python -m civitai.server --port 8080

Opens http://localhost:8000 in your browser automatically.
"""

from __future__ import annotations

import json
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from pathlib import Path
import argparse

_EXPORT_DIR = Path(__file__).parent.parent / "export"

from . import Civitai
from .client import CivitaiError
from .report import generate_html

# ---------------------------------------------------------------------------
# Embedded UI
# ---------------------------------------------------------------------------

_UI = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Civitai Bounty Reporter</title>

<style>
  :root {
    --bg:#0d0d1a; --surface:#16213e; --border:#2a2a4a;
    --accent:#e879f9; --accent2:#818cf8; --text:#e2e8f0; --muted:#64748b;
    --input-bg:#0d0d1a; --btn:#7c3aed; --btn-hover:#6d28d9;
    --error:#f87171; --success:#4ade80;
  }
  [data-theme="light"] {
    --bg:#f8fafc; --surface:#fff; --border:#e2e8f0;
    --accent:#9333ea; --accent2:#6366f1; --text:#1e293b; --muted:#94a3b8;
    --input-bg:#fff; --btn:#7c3aed; --btn-hover:#6d28d9;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font-family:system-ui,sans-serif;
         min-height:100vh; display:flex; flex-direction:column; align-items:center;
         justify-content:center; padding:24px; }
  .card { background:var(--surface); border:1px solid var(--border); border-radius:14px;
          padding:36px 40px; width:100%; max-width:480px; box-shadow:0 8px 40px #0006; }
  h1 { font-size:1.5rem; font-weight:700; margin-bottom:6px;
       background:linear-gradient(90deg,var(--accent),var(--accent2));
       -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
  .subtitle { color:var(--muted); font-size:0.85rem; margin-bottom:28px; }
  label { display:block; font-size:0.8rem; font-weight:600; color:var(--muted);
          text-transform:uppercase; letter-spacing:.05em; margin-bottom:6px; }
  input[type=text], input[type=password], input[type=number] {
    width:100%; background:var(--input-bg); border:1px solid var(--border);
    border-radius:8px; color:var(--text); font-size:0.95rem;
    padding:10px 12px; outline:none; transition:border-color .15s;
  }
  input:focus { border-color:var(--accent2); }
  .field { margin-bottom:18px; }
  .row { display:flex; gap:12px; }
  .row .field { flex:1; }
  .hint { font-size:0.72rem; color:var(--muted); margin-top:5px; }
  .hint a { color:var(--accent2); }
  .warning { margin-top:12px; padding:9px 12px; background:#ca8a0418;
    border:1px solid #ca8a0455; border-radius:8px; font-size:0.78rem;
    color:#fbbf24; line-height:1.4; }

  button[type=submit] {
    width:100%; padding:12px; background:var(--btn); color:#fff;
    border:none; border-radius:8px; font-size:1rem; font-weight:600;
    cursor:pointer; transition:background .15s; margin-top:4px;
    display:flex; align-items:center; justify-content:center; gap:8px;
  }
  button[type=submit]:hover { background:var(--btn-hover); }
  button[type=submit]:disabled { opacity:.5; cursor:not-allowed; }

  .spinner { width:18px; height:18px; border:2px solid #ffffff44;
             border-top-color:#fff; border-radius:50%; animation:spin .7s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }

  .msg { margin-top:16px; padding:10px 14px; border-radius:8px;
         font-size:0.88rem; display:none; }
  .msg.error { background:#f8717122; border:1px solid var(--error); color:var(--error); }
  .msg.success { background:#4ade8022; border:1px solid var(--success); color:var(--success); }

  .theme-toggle { position:fixed; top:18px; right:18px; background:var(--surface);
    border:1px solid var(--border); border-radius:20px; padding:6px 14px;
    cursor:pointer; font-size:0.8rem; color:var(--muted); }
  .theme-toggle:hover { color:var(--text); }

  .token-row { display:flex; gap:8px; }
  .token-row input { flex:1; }
  .eye-btn { background:none; border:1px solid var(--border); border-radius:8px;
    color:var(--muted); cursor:pointer; padding:0 12px; font-size:1rem; }
  .eye-btn:hover { color:var(--text); }
</style>
</head>
<body>

<button class="theme-toggle" onclick="toggleTheme()">🌙 / ☀️</button>

<div class="card">
  <h1>Civitai Bounty Reporter</h1>
  <p class="subtitle">Generate a full HTML report for a Civitai bounty.</p>

  <form id="form" onsubmit="handleSubmit(event)">
    <div class="field">
      <label>API Token</label>
      <div class="token-row">
        <input type="password" id="token" placeholder="ab12cd34…" autocomplete="off" required>
        <button type="button" class="eye-btn" onclick="toggleToken()" title="Afficher/masquer">👁</button>
      </div>
      <div class="hint">
        Generate a token at
        <a href="https://civitai.red/user/account" target="_blank">civitai.red → account settings</a>.
        Stored only in your browser (localStorage).
      </div>
    </div>

    <div class="row">
      <div class="field">
        <label>Bounty ID</label>
        <input type="number" id="bounty_id" placeholder="12018" min="1" required>
        <div class="hint">The number in the URL civitai.red/bounties/<strong>12018</strong>/…</div>
      </div>
      <div class="field">
        <label>Report theme</label>
        <select id="theme_sel" style="width:100%;background:var(--input-bg);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:.95rem;padding:10px 12px;outline:none;">
          <option value="dark">🌙 Dark</option>
          <option value="light">☀️ Light</option>
        </select>
      </div>
    </div>

    <button type="submit" id="btn">
      <span id="btn-text">Generate report</span>
    </button>
    <div class="warning">
      ⚠️ This fetches every entry, reaction and prompt from the API.
      For large bounties (300+ entries) this may take 20–30 seconds — please wait.
    </div>
  </form>

  <div class="msg error" id="err"></div>
  <div class="msg success" id="ok"></div>
</div>

<script>
const LS_TOKEN = 'civitai_token';
const LS_THEME = 'civitai_ui_theme';

// Restore saved values
const saved = localStorage.getItem(LS_TOKEN);
if (saved) document.getElementById('token').value = saved;

const savedTheme = localStorage.getItem(LS_THEME) || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);

function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem(LS_THEME, next);
}

function toggleToken() {
  const el = document.getElementById('token');
  el.type = el.type === 'password' ? 'text' : 'password';
}

async function handleSubmit(e) {
  e.preventDefault();
  const token = document.getElementById('token').value.trim();
  const bounty_id = document.getElementById('bounty_id').value.trim();
  const theme = document.getElementById('theme_sel').value;

  localStorage.setItem(LS_TOKEN, token);

  // UI loading state
  const btn = document.getElementById('btn');
  const btnText = document.getElementById('btn-text');
  btn.disabled = true;
  btnText.innerHTML = '<span class="spinner"></span> Loading…';
  document.getElementById('err').style.display = 'none';
  document.getElementById('ok').style.display = 'none';

  try {
    const resp = await fetch('/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token, bounty_id: parseInt(bounty_id), theme}),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || `Erreur ${resp.status}`);

    // Open the report HTML in a new tab
    const blob = new Blob([data.html], {type: 'text/html'});
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');

    const ok = document.getElementById('ok');
    ok.textContent = `✓ Report for bounty #${bounty_id} generated — opened in a new tab`;
    ok.style.display = 'block';
  } catch(err) {
    const el = document.getElementById('err');
    el.textContent = '✗ ' + err.message;
    el.style.display = 'block';
  } finally {
    btn.disabled = false;
    btnText.textContent = 'Generate report';
  }
}
</script>
</body>
</html>"""

# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # silence default access log

    def do_GET(self):
        self._respond(200, "text/html; charset=utf-8", _UI.encode())

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        if path == "/save-scores":
            try:
                payload = json.loads(body)
                bounty_id = int(payload["bounty_id"])
                scores = payload.get("scores", {})
                comments = payload.get("comments", {})
                highlights = payload.get("highlights", [])
                _EXPORT_DIR.mkdir(exist_ok=True)
                (_EXPORT_DIR / f"{bounty_id}.json").write_text(json.dumps({"scores": scores, "comments": comments, "highlights": highlights}))
                self._json(200, {"ok": True})
            except Exception:
                self._json(500, {"error": traceback.format_exc().splitlines()[-1]})
            return

        if path != "/generate":
            self._respond(404, "text/plain", b"Not found")
            return

        try:
            payload = json.loads(body)
            token = payload.get("token", "").strip()
            bounty_id = int(payload["bounty_id"])
            theme = payload.get("theme", "dark")

            scores_path = _EXPORT_DIR / f"{bounty_id}.json"
            saved = json.loads(scores_path.read_text()) if scores_path.exists() else {}
            saved_scores = saved.get("scores", saved) if isinstance(saved, dict) else {}
            saved_comments = saved.get("comments", {}) if isinstance(saved, dict) else {}
            saved_highlights = saved.get("highlights", []) if isinstance(saved, dict) else []

            civ = Civitai(api_token=token or None)
            report = civ.bounties.full_report(bounty_id)
            server_url = f"http://localhost:{self.server.server_address[1]}"
            html_out = generate_html(report, bounty_id, theme=theme, saved_scores=saved_scores, saved_comments=saved_comments, saved_highlights=saved_highlights, server_url=server_url)

            self._json(200, {"html": html_out})

        except CivitaiError as e:
            self._json(400, {"error": str(e)})
        except Exception as e:
            msg = traceback.format_exc().splitlines()[-1]
            if any(f"HTTP {code}" in msg for code in ["520","521","522","523","524","525","526"]):
                msg = f"Civitai's servers returned a Cloudflare error ({msg.split('HTTP')[1].strip().split(':')[0].strip()}) — this is a temporary issue on their end. Please try again in a few minutes."
            self._json(500, {"error": msg})

    def _respond(self, code: int, ctype: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, data: dict):
        body = json.dumps(data).encode()
        self._respond(code, "application/json; charset=utf-8", body)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Civitai Bounty Reporter — UI locale")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    server = HTTPServer(("127.0.0.1", args.port), _Handler)
    url = f"http://localhost:{args.port}"
    print(f"  Civitai Bounty Reporter  →  {url}")
    print("  Ctrl+C pour arrêter\n")

    if not args.no_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServeur arrêté.")


if __name__ == "__main__":
    main()
