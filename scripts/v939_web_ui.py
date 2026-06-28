#!/usr/bin/env python3
"""
v939_web_ui.py — WEB UI v9.39 with SSE streaming
==================================================
HTTP server with:
- Real-time streaming LLM responses (Server-Sent Events)
- Live gate status dashboard
- Cache management
- Prometheus metrics link
- Daemon cluster status

Usage:
    python3 v939_web_ui.py              # :8765
    python3 v939_web_ui.py --port 9000
"""
import http.server
import json
import os
import socketserver
import subprocess
import sys
import time
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 8765
DAEMON = "/home/z/my-project/scripts/v937_daemon.py"
LLM_CLIENT = "/home/z/my-project/scripts/v938_llm_client.py"
CLUSTER = "/home/z/my-project/scripts/v939_cluster.py"


def daemon_cmd(cmd, args=None, timeout=120):
    try:
        cmd_args = ["--args"] + (args or [])
        result = subprocess.run(
            ["python3", DAEMON, "--run", cmd] + cmd_args,
            capture_output=True, text=True, timeout=timeout
        )
        return json.loads(result.stdout.strip())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def llm_chat_stream(prompt, system=""):
    """Generator that yields SSE chunks for streaming LLM response.
    
    Simulates streaming by yielding the response in chunks.
    (z-ai SDK supports --stream flag, but for simplicity we chunk the final response.)
    """
    try:
        # Get full response first
        result = subprocess.run(
            ["python3", LLM_CLIENT, "chat", "--prompt", prompt, "--system", system, "-v"],
            capture_output=True, text=True, timeout=180
        )
        data = json.loads(result.stdout.strip())
        
        content = data.get("content", "")
        model = data.get("model", "unknown")
        cached = data.get("cached", False)
        tokens = data.get("tokens", 0)
        attempts = data.get("attempts", 0)
        chain = data.get("provider_chain", [])
        
        # Yield metadata first
        yield f"data: {json.dumps({'type': 'meta', 'model': model, 'cached': cached, 'tokens': tokens, 'attempts': attempts, 'chain': chain})}\n\n"
        
        # Stream content in word chunks
        words = content.split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
            time.sleep(0.02)  # 20ms per word for visible streaming
        
        # Done
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"


HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
<title>v9.39 Control Panel</title>
<meta charset="utf-8">
<style>
* { box-sizing: border-box; }
body { font-family: -apple-system, sans-serif; margin: 20px; background: #0f172a; color: #e2e8f0; }
h1 { color: #38bdf8; }
h2 { color: #94a3b8; border-bottom: 1px solid #334155; padding-bottom: 5px; }
.card { background: #1e293b; padding: 15px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.3); margin-bottom: 15px; border: 1px solid #334155; }
.summary { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 20px; }
.stat { background: #2563eb; color: white; padding: 12px; border-radius: 8px; text-align: center; }
.stat .value { font-size: 24px; font-weight: bold; }
.stat .label { font-size: 10px; opacity: 0.8; text-transform: uppercase; }
textarea, input[type=text] { width: 100%; padding: 8px; border: 1px solid #475569; border-radius: 4px; background: #0f172a; color: #e2e8f0; font-family: monospace; font-size: 13px; }
textarea { min-height: 60px; }
button { background: #2563eb; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; transition: background 0.2s; }
button:hover { background: #1d4ed8; }
button.danger { background: #dc2626; }
button.danger:hover { background: #b91c1c; }
button.success { background: #16a34a; }
.result { background: #0f172a; padding: 10px; border-radius: 4px; margin-top: 10px; white-space: pre-wrap; font-size: 12px; max-height: 300px; overflow-y: auto; border: 1px solid #334155; }
.gate-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.gate { background: #334155; padding: 8px; border-radius: 4px; font-size: 12px; }
.gate-name { font-weight: bold; color: #cbd5e1; }
.pass { color: #4ade80; font-weight: bold; }
.fail { color: #f87171; font-weight: bold; }
.stream { border-left: 3px solid #38bdf8; padding-left: 10px; min-height: 30px; }
a { color: #38bdf8; }
.tab { display: inline-block; padding: 8px 16px; background: #1e293b; border-radius: 4px 4px 0 0; cursor: pointer; border: 1px solid #334155; }
.tab.active { background: #2563eb; }
#loading { display: none; color: #94a3b8; font-size: 12px; }
</style>
</head>
<body>
<h1>v9.39 Control Panel</h1>

<div class="summary">
    <div class="stat"><div class="value" id="stat-gates">-</div><div class="label">Gates</div></div>
    <div class="stat"><div class="value" id="stat-cache">-</div><div class="label">Cache</div></div>
    <div class="stat"><div class="value" id="stat-tokens">-</div><div class="label">Tokens Saved</div></div>
    <div class="stat"><div class="value" id="stat-uptime">-</div><div class="label">Uptime</div></div>
    <div class="stat"><div class="value" id="stat-workers">-</div><div class="label">Workers</div></div>
</div>

<h2>Gate Status</h2>
<div class="card">
    <button onclick="runAllGates()">Run All Gates</button>
    <span id="loading">Running...</span>
    <div class="gate-grid" id="gateGrid" style="margin-top: 10px;">
        <div class="gate"><div class="gate-name">Click "Run All Gates"</div></div>
    </div>
</div>

<h2>LLM Chat (streaming)</h2>
<div class="card">
    <input type="text" id="system" placeholder="System prompt (optional)" style="margin-bottom: 5px;">
    <textarea id="prompt" placeholder="Enter your prompt here..."></textarea>
    <div style="margin-top: 5px;">
        <button onclick="llmStream()">Send (stream)</button>
        <button onclick="clearCache()" class="danger">Clear Cache</button>
        <button onclick="warmupCache()" class="success">Warmup Cache</button>
        <label><input type="checkbox" id="noCache"> Skip cache</label>
    </div>
    <div class="result stream" id="llmResult">Streaming results appear here...</div>
    <div id="llmMeta" style="font-size: 11px; color: #94a3b8; margin-top: 5px;"></div>
</div>

<h2>Cluster & Monitoring</h2>
<div class="card">
    <button onclick="clusterStatus()">Cluster Status</button>
    <button onclick="clusterStart()">Start Cluster (3 workers)</button>
    <button onclick="clusterStop()" class="danger">Stop Cluster</button>
    <br><br>
    <a href="http://localhost:9090/metrics" target="_blank">Prometheus Metrics →</a>
    <div class="result" id="clusterResult">Click to check cluster...</div>
</div>

<script>
async function api(path, body) {
    const resp = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    return resp.json();
}

async function runAllGates() {
    document.getElementById('loading').style.display = 'inline';
    const models = [
        {cmd: 'g0_check', args: [], name: 'G0 Immutable Core'},
        {cmd: 'z3_verify', args: [], name: 'G0-Z3 Formal Verify'},
        {cmd: 'bert_check_primary_goal', args: [], name: 'G58 BERT (all-MiniLM)'},
        {cmd: 'bert_check_primary_goal', args: ['sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'], name: 'G60 Multilingual'},
        {cmd: 'bert_check_primary_goal', args: ['sentence-transformers/paraphrase-MiniLM-L6-v2'], name: 'G61 Paraphrase'},
    ];
    const grid = document.getElementById('gateGrid');
    grid.innerHTML = '';
    let passCount = 0;
    
    for (const m of models) {
        const r = await api('/api/daemon', {cmd: m.cmd, args: m.args});
        let pass = false, detail = '';
        if (r.ok && r.result) {
            if (m.cmd === 'g0_check') { pass = r.result.pass; detail = r.result.actual_hash || ''; }
            else if (m.cmd === 'z3_verify') { pass = r.result.proven; detail = r.result.time_sec + 's'; }
            else { pass = r.result.pass; detail = 'sim=' + (r.result.similarity||0).toFixed(4); }
        }
        if (pass) passCount++;
        grid.innerHTML += `<div class="gate"><div class="gate-name">${m.name}</div><div class="gate-result"><span class="${pass?'pass':'fail'}">${pass?'PASS':'FAIL'}</span> ${detail}</div></div>`;
    }
    
    document.getElementById('stat-gates').textContent = passCount + '/' + models.length;
    document.getElementById('loading').style.display = 'none';
}

async function llmStream() {
    const prompt = document.getElementById('prompt').value;
    const system = document.getElementById('system').value;
    const noCache = document.getElementById('noCache').checked;
    
    document.getElementById('llmResult').innerHTML = '<span style="color:#94a3b8">Streaming...</span>';
    document.getElementById('llmMeta').textContent = '';
    
    const evtSource = new EventSource('/api/llm-stream?prompt=' + encodeURIComponent(prompt) + '&system=' + encodeURIComponent(system) + '&no_cache=' + noCache);
    let content = '';
    
    evtSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.type === 'meta') {
            document.getElementById('llmMeta').textContent = `Model: ${data.model} | Cached: ${data.cached} | Tokens: ${data.tokens} | Attempts: ${data.attempts} | Chain: ${data.chain.join(' → ')}`;
        } else if (data.type === 'chunk') {
            content += data.content;
            document.getElementById('llmResult').innerHTML = content;
        } else if (data.type === 'done') {
            evtSource.close();
        } else if (data.type === 'error') {
            document.getElementById('llmResult').innerHTML = '<span style="color:#f87171">ERROR: ' + data.error + '</span>';
            evtSource.close();
        }
    };
    
    evtSource.onerror = function() { evtSource.close(); };
    
    setTimeout(updateCacheStats, 1000);
}

async function clearCache() {
    const r = await api('/api/cache-clear', {});
    document.getElementById('llmResult').textContent = 'Cleared: ' + (r.deleted || 0) + ' entries';
    updateCacheStats();
}

async function warmupCache() {
    document.getElementById('llmResult').innerHTML = '<span style="color:#94a3b8">Warming cache (16 prompts, parallel)...</span>';
    const r = await api('/api/warmup', {});
    document.getElementById('llmResult').textContent = r.output || 'Warmup done';
    updateCacheStats();
}

async function clusterStatus() {
    const r = await api('/api/cluster', {action: 'status'});
    document.getElementById('clusterResult').textContent = JSON.stringify(r, null, 2);
    if (r.workers) document.getElementById('stat-workers').textContent = r.workers;
}

async function clusterStart() {
    document.getElementById('clusterResult').textContent = 'Starting cluster...';
    const r = await api('/api/cluster', {action: 'start', workers: 3});
    document.getElementById('clusterResult').textContent = JSON.stringify(r, null, 2);
}

async function clusterStop() {
    const r = await api('/api/cluster', {action: 'stop'});
    document.getElementById('clusterResult').textContent = JSON.stringify(r, null, 2);
}

async function updateCacheStats() {
    const r = await api('/api/daemon', {cmd: 'llm_cache_stats'});
    if (r.ok && r.result) {
        document.getElementById('stat-cache').textContent = r.result.total_entries;
        document.getElementById('stat-tokens').textContent = r.result.total_tokens_saved;
    }
}

// Auto-check health on load
fetch('/api/daemon', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({cmd:'health'})})
    .then(r => r.json())
    .then(r => { if (r.ok) document.getElementById('stat-uptime').textContent = Math.round(r.result.uptime_sec) + 's'; });
updateCacheStats();
</script>
</body>
</html>"""


class V939Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        
        elif parsed.path == "/api/llm-stream":
            # SSE streaming endpoint
            params = parse_qs(parsed.query)
            prompt = params.get("prompt", [""])[0]
            system = params.get("system", [""])[0]
            
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            
            for chunk in llm_chat_stream(prompt, system):
                try:
                    self.wfile.write(chunk.encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    break  # client disconnected
        
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

        elif self.path == "/api/cache-clear":
            try:
                result = subprocess.run(["python3", LLM_CLIENT, "cache-clear"], capture_output=True, text=True, timeout=10)
                import re
                m = re.search(r'cleared (\d+)', result.stdout)
                self._json_response({"deleted": int(m.group(1)) if m else 0})
            except Exception as e:
                self._json_response({"error": str(e)})

        elif self.path == "/api/warmup":
            try:
                result = subprocess.run(["python3", "/home/z/my-project/scripts/v939_warmup.py", "--parallel"], capture_output=True, text=True, timeout=120)
                self._json_response({"output": result.stdout[-500:]})
            except Exception as e:
                self._json_response({"error": str(e)})

        elif self.path == "/api/cluster":
            action = data.get("action")
            try:
                if action == "status":
                    result = subprocess.run(["python3", CLUSTER, "--status"], capture_output=True, text=True, timeout=10)
                    workers = result.stdout.count("Worker")
                    self._json_response({"status": result.stdout, "workers": workers})
                elif action == "start":
                    workers = data.get("workers", 3)
                    result = subprocess.run(["python3", CLUSTER, "--start", "--workers", str(workers)], capture_output=True, text=True, timeout=60)
                    self._json_response({"output": result.stdout[-500:]})
                elif action == "stop":
                    result = subprocess.run(["python3", CLUSTER, "--stop"], capture_output=True, text=True, timeout=15)
                    self._json_response({"output": result.stdout})
                else:
                    self._json_response({"error": "unknown action"})
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
        pass


def main():
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else PORT
    print(f"v9.39 Web UI on http://localhost:{port}")
    print(f"Prometheus metrics: http://localhost:9090/metrics")
    with socketserver.TCPServer(("localhost", port), V939Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
