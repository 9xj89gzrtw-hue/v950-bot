#!/usr/bin/env python3
"""
v938_web_ui.py — WEB UI for daemon v9.38
==========================================
HTTP server on localhost:8765 providing:
- Dashboard with all gates status
- LLM chat interface (with cache + fallback)
- Cache statistics
- Daemon health
- Cost/latency dashboard link

Usage:
    python3 v938_web_ui.py              # start server on :8765
    python3 v938_web_ui.py --port 9000  # custom port
"""
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 8765
DAEMON = "/home/z/my-project/scripts/v937_daemon.py"
LLM_CLIENT = "/home/z/my-project/scripts/v938_llm_client.py"


def daemon_cmd(cmd, args=None, timeout=120):
    """Send command to daemon, return parsed JSON."""
    try:
        cmd_args = ["--args"] + (args or [])
        result = subprocess.run(
            ["python3", DAEMON, "--run", cmd] + cmd_args,
            capture_output=True, text=True, timeout=timeout
        )
        return json.loads(result.stdout.strip())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def llm_chat(prompt, system=""):
    """Call LLM client."""
    try:
        result = subprocess.run(
            ["python3", LLM_CLIENT, "chat", "--prompt", prompt, "--system", system],
            capture_output=True, text=True, timeout=180
        )
        return json.loads(result.stdout.strip())
    except Exception as e:
        return {"error": str(e)}


HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
<title>v9.38 Daemon Control Panel</title>
<meta charset="utf-8">
<style>
body { font-family: -apple-system, sans-serif; margin: 20px; background: #f0f2f5; }
h1 { color: #1a1a1a; }
h2 { color: #333; border-bottom: 2px solid #ddd; padding-bottom: 5px; }
.card { background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 15px; }
.summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
.stat { background: #2563eb; color: white; padding: 15px; border-radius: 8px; text-align: center; }
.stat .value { font-size: 28px; font-weight: bold; }
.stat .label { font-size: 11px; opacity: 0.9; }
input, textarea, button { font-family: monospace; font-size: 13px; }
textarea { width: 100%; min-height: 60px; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
input[type=text] { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; margin-bottom: 5px; }
button { background: #2563eb; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; }
button:hover { background: #1d4ed8; }
button:disabled { background: #999; }
.result { background: #f8f9fa; padding: 10px; border-radius: 4px; margin-top: 10px; white-space: pre-wrap; font-size: 12px; max-height: 300px; overflow-y: auto; }
.gate-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.gate { background: #f8f9fa; padding: 10px; border-radius: 4px; font-size: 12px; }
.gate-name { font-weight: bold; color: #333; }
.gate-result { color: #666; margin-top: 5px; }
.pass { color: #16a34a; font-weight: bold; }
.fail { color: #dc2626; font-weight: bold; }
#loading { display: none; color: #666; font-size: 12px; }
</style>
</head>
<body>
<h1>v9.38 Daemon Control Panel</h1>

<div class="summary" id="summary">
    <div class="stat"><div class="value" id="stat-gates">-</div><div class="label">Gates Tested</div></div>
    <div class="stat"><div class="value" id="stat-cache">-</div><div class="label">Cache Entries</div></div>
    <div class="stat"><div class="value" id="stat-tokens">-</div><div class="label">Tokens Saved</div></div>
    <div class="stat"><div class="value" id="stat-uptime">-</div><div class="label">Daemon Uptime</div></div>
</div>

<h2>Gate Status (live)</h2>
<div class="card">
    <button onclick="runAllGates()">Run All Gates</button>
    <span id="loading">Running...</span>
    <div class="gate-grid" id="gateGrid" style="margin-top: 10px;">
        <div class="gate"><div class="gate-name">Click "Run All Gates" to test</div></div>
    </div>
</div>

<h2>LLM Chat (with cache + fallback)</h2>
<div class="card">
    <input type="text" id="system" placeholder="System prompt (optional)">
    <textarea id="prompt" placeholder="Enter your prompt here..."></textarea>
    <div style="margin-top: 5px;">
        <button onclick="llmChat()">Send</button>
        <button onclick="clearCache()" style="background: #dc2626;">Clear Cache</button>
        <label><input type="checkbox" id="noCache"> Skip cache</label>
    </div>
    <div class="result" id="llmResult">Results will appear here...</div>
</div>

<h2>Daemon Health</h2>
<div class="card">
    <button onclick="checkHealth()">Check Health</button>
    <div class="result" id="healthResult">Click to check...</div>
</div>

<script>
async function api(path, body) {
    const resp = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    return resp.json();
}

async function runAllGates() {
    document.getElementById('loading').style.display = 'inline';
    const gates = ['g0_check', 'z3_verify', 'bert_check_primary_goal'];
    const models = [
        {cmd: 'bert_check_primary_goal', args: [], name: 'G58 BERT (all-MiniLM)'},
        {cmd: 'bert_check_primary_goal', args: ['sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'], name: 'G60 Multilingual'},
        {cmd: 'bert_check_primary_goal', args: ['sentence-transformers/paraphrase-MiniLM-L6-v2'], name: 'G61 Paraphrase'},
    ];
    const grid = document.getElementById('gateGrid');
    grid.innerHTML = '';
    let passCount = 0;
    
    // G0
    let r = await api('/api/daemon', {cmd: 'g0_check'});
    let pass = r.ok && r.result && r.result.pass;
    if (pass) passCount++;
    grid.innerHTML += `<div class="gate"><div class="gate-name">G0 Immutable Core</div><div class="gate-result"><span class="${pass?'pass':'fail'}">${pass?'PASS':'FAIL'}</span> ${r.result?r.result.actual_hash||'':''}</div></div>`;
    
    // Z3
    r = await api('/api/daemon', {cmd: 'z3_verify'});
    pass = r.ok && r.result && r.result.proven;
    if (pass) passCount++;
    grid.innerHTML += `<div class="gate"><div class="gate-name">G0-Z3 Formal Verify</div><div class="gate-result"><span class="${pass?'pass':'fail'}">${pass?'PROVEN':'FAIL'}</span> ${r.result?(r.result.time_sec+'s'):''}</div></div>`;
    
    // BERT gates
    for (const m of models) {
        r = await api('/api/daemon', {cmd: m.cmd, args: m.args});
        pass = r.ok && r.result && r.result.pass;
        if (pass) passCount++;
        const sim = r.result ? r.result.similarity : 0;
        grid.innerHTML += `<div class="gate"><div class="gate-name">${m.name}</div><div class="gate-result"><span class="${pass?'pass':'fail'}">${pass?'PASS':'FAIL'}</span> sim=${sim?sim.toFixed(4):'?'}</div></div>`;
    }
    
    document.getElementById('stat-gates').textContent = passCount + '/' + (3 + models.length);
    document.getElementById('loading').style.display = 'none';
}

async function llmChat() {
    const prompt = document.getElementById('prompt').value;
    const system = document.getElementById('system').value;
    const noCache = document.getElementById('noCache').checked;
    document.getElementById('llmResult').textContent = 'Sending...';
    const r = await api('/api/llm', {prompt, system, no_cache: noCache});
    if (r.error) {
        document.getElementById('llmResult').textContent = 'ERROR: ' + r.error;
    } else {
        document.getElementById('llmResult').textContent = 
            'Model: ' + r.model + '\\n' +
            'Cached: ' + r.cached + '\\n' +
            'Attempts: ' + r.attempts + '\\n' +
            'Tokens: ' + r.tokens + '\\n' +
            'Chain: ' + (r.provider_chain||[]).join(' → ') + '\\n\\n' +
            'Response:\\n' + r.content;
    }
    updateCacheStats();
}

async function clearCache() {
    const r = await api('/api/cache-clear', {});
    document.getElementById('llmResult').textContent = 'Cleared: ' + (r.deleted || 0) + ' entries';
    updateCacheStats();
}

async function checkHealth() {
    const r = await api('/api/daemon', {cmd: 'health'});
    document.getElementById('healthResult').textContent = JSON.stringify(r, null, 2);
    if (r.ok && r.result) {
        document.getElementById('stat-uptime').textContent = Math.round(r.result.uptime_sec) + 's';
    }
}

async function updateCacheStats() {
    const r = await api('/api/daemon', {cmd: 'llm_cache_stats'});
    if (r.ok && r.result) {
        document.getElementById('stat-cache').textContent = r.result.total_entries;
        document.getElementById('stat-tokens').textContent = r.result.total_tokens_saved;
    }
}

// Auto-update on load
checkHealth();
updateCacheStats();
</script>
</body>
</html>"""


class V938Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}

        if self.path == "/api/daemon":
            cmd = data.get("cmd")
            args = data.get("args", [])
            result = daemon_cmd(cmd, args)
            self._json_response(result)

        elif self.path == "/api/llm":
            prompt = data.get("prompt", "")
            system = data.get("system", "")
            result = llm_chat(prompt, system)
            self._json_response(result)

        elif self.path == "/api/cache-clear":
            try:
                result = subprocess.run(
                    ["python3", LLM_CLIENT, "cache-clear"],
                    capture_output=True, text=True, timeout=10
                )
                output = result.stdout.strip()
                # Parse "cleared N entries"
                import re
                m = re.search(r'cleared (\d+)', output)
                deleted = int(m.group(1)) if m else 0
                self._json_response({"deleted": deleted})
            except Exception as e:
                self._json_response({"error": str(e)})
        else:
            self.send_response(404)
            self.end_headers()

    def _json_response(self, obj):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        pass  # suppress logs


def main():
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else PORT
    
    print(f"v9.38 Web UI starting on http://localhost:{port}")
    print(f"Open in browser: http://localhost:{port}")
    print(f"Press Ctrl+C to stop")
    
    with socketserver.TCPServer(("localhost", port), V938Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
            httpd.shutdown()


if __name__ == "__main__":
    main()
