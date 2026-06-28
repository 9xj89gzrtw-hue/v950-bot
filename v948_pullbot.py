#!/usr/bin/env python3
"""
v948_pullbot.py — TELEGRAM BOT (Render.com compatible)
=======================================================
Self-contained: no hardcoded paths, works from any directory.
Uses environment variables for Telegram credentials.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# Use environment variables (Render.com sets these)
# Fallback to config file if env not set
def load_config():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if bot_token and chat_id:
        return {"bot_token": bot_token, "chat_id": chat_id}
    # Try config file
    config_path = os.path.join(os.path.dirname(__file__), "v944_telegram_config.json")
    if os.path.exists(config_path):
        return json.loads(Path(config_path).read_text())
    return {"bot_token": "", "chat_id": ""}

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v948_pullbot_state.json")
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")


def log(msg):
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[{ts}] {msg}", flush=True)


def tg_send(token, chat_id, text):
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": chunk}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=30)
        except Exception as e:
            log(f"SEND ERROR: {e}")
        time.sleep(0.2)


def tg_get_updates(token, offset, timeout=5):
    url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout={timeout}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout + 10)
        data = json.loads(resp.read())
        if data.get("ok"):
            return data.get("result", [])
    except Exception as e:
        log(f"getUpdates error: {e}")
    return []


def cmd_status(args, config):
    lines = ["🤖 v9.56 Status\n"]
    
    # Check disk
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        disk_line = result.stdout.strip().split("\n")[-1]
        lines.append(f"💾 Disk: {disk_line.split()[-2]} used")
    except:
        pass
    
    # Check if scripts dir exists
    if os.path.exists(SCRIPTS_DIR):
        scripts_count = len([f for f in os.listdir(SCRIPTS_DIR) if f.endswith('.py')])
        lines.append(f"📁 Scripts: {scripts_count} files")
    else:
        lines.append("📁 Scripts: not available (minimal deploy)")
    
    lines.append(f"📄 State: {os.path.exists(STATE_FILE)}")
    lines.append(f"🌍 Environment: {os.environ.get('RENDER', 'not Render')}")
    
    return "\n".join(lines)


def cmd_help(args, config):
    return ("📚 Commands:\n"
            "/status — infrastructure\n"
            "/chat <text> — LLM chat\n"
            "/help — this message")


def cmd_chat(args, config):
    if not args:
        return "Usage: /chat <message>"
    prompt = " ".join(args)
    
    # Try z-ai SDK
    try:
        result = subprocess.run(
            ["npx", "z-ai-web-dev-sdk", "chat", "--prompt", prompt],
            capture_output=True, text=True, timeout=60
        )
        import re
        m = re.search(r'\{\s*"choices"', result.stdout, re.S)
        if m:
            start = m.start()
            depth = 0
            for i in range(start, len(result.stdout)):
                if result.stdout[i] == '{': depth += 1
                elif result.stdout[i] == '}':
                    depth -= 1
                    if depth == 0:
                        obj = json.loads(result.stdout[start:i+1])
                        content = obj["choices"][0]["message"]["content"]
                        model = obj.get("model", "?")
                        return f"🤖 {model}\n\n{content}"
    except subprocess.TimeoutExpired:
        pass
    except Exception as e:
        log(f"z-ai error: {e}")
    
    # Fallback: Pollinations
    try:
        payload = json.dumps({
            "model": "openai",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://text.pollinations.ai/openai",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        return f"🤖 gpt-oss-20b (fallback)\n\n{content}"
    except Exception as e:
        return f"❌ LLM error: {e}"


COMMANDS = {
    "start": lambda a, c: cmd_help(a, c),
    "help": cmd_help,
    "status": cmd_status,
    "chat": cmd_chat,
}


def handle_message(text, config):
    try:
        if not text.startswith("/"):
            return "Send /help for commands"
        parts = text[1:].split()
        cmd = parts[0].lower() if parts else ""
        args = parts[1:]
        handler = COMMANDS.get(cmd)
        if not handler:
            return f"Unknown: /{cmd}\nSend /help"
        return handler(args, config)
    except Exception as e:
        return f"❌ Error: {e}"


def process_once(config):
    token = config["bot_token"]
    chat_id = str(config["chat_id"])
    
    state = {"last_update_id": 0}
    if os.path.exists(STATE_FILE):
        try:
            state = json.loads(Path(STATE_FILE).read_text())
        except:
            pass
    
    offset = state.get("last_update_id", 0) + 1
    updates = tg_get_updates(token, offset, timeout=5)
    
    if not updates:
        return 0
    
    processed = 0
    for update in updates:
        update_id = update.get("update_id", 0)
        state["last_update_id"] = max(state.get("last_update_id", 0), update_id)
        
        message = update.get("message", {})
        text = message.get("text", "")
        from_chat_id = str(message.get("chat", {}).get("id", ""))
        
        if from_chat_id != chat_id or not text:
            continue
        
        log(f"RECEIVED: {text[:80]}")
        response = handle_message(text, config)
        tg_send(token, from_chat_id, response)
        log(f"SENT: {response[:80]}")
        processed += 1
    
    Path(STATE_FILE).write_text(json.dumps(state))
    return processed


def run_loop(interval=10):
    config = load_config()
    if not config.get("bot_token"):
        log("ERROR: No TELEGRAM_BOT_TOKEN set!")
        sys.exit(1)
    
    # Start health check HTTP server (for Render port detection)
    try:
        health_port = start_health_server()
        log(f"Health server on port {health_port}")
    except Exception as e:
        log(f"Health server failed (non-critical): {e}")
    
    log(f"v9.56 bot starting (interval={interval}s)")
    log(f"Chat ID: {config.get('chat_id')}")
    
    # Send startup notification
    tg_send(config["bot_token"], str(config["chat_id"]), 
            "✅ v9.56 bot started on Render!\n\nSend /status or /chat <message>")
    
    while True:
        try:
            count = process_once(config)
            if count > 0:
                log(f"Processed {count} messages")
        except Exception as e:
            log(f"LOOP ERROR: {e}")
        time.sleep(interval)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=10)
    args = parser.parse_args()
    
    if args.loop:
        run_loop(args.interval)
    else:
        config = load_config()
        count = process_once(config)
        log(f"One-shot: processed {count} messages")


if __name__ == "__main__":
    main()


# ============================================================================
# MINIMAL HTTP SERVER (for Render port detection)
# ============================================================================
def start_health_server():
    """Start minimal HTTP server on $PORT for Render health check."""
    import http.server
    port = int(os.environ.get("PORT", 10000))
    
    class HealthHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK")
            else:
                self.send_response(404)
                self.end_headers()
        def log_message(self, *args):
            pass  # silent
    
    server = http.server.HTTPServer(("0.0.0.0", port), HealthHandler)
    import threading
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return port
