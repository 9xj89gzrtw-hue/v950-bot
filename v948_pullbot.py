#!/usr/bin/env python3
"""Minimal webhook bot for Render — fast build, reliable."""
import json, os, time, urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8736969974:AAG66M9I0uGwRUksTt1iJt7v-n-f7T7BpnE")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "396449039")
PORT = int(os.environ.get("PORT", 10000))

def llm(system, user, max_tokens=1500):
    """Pollinations — no auth, no deps, always works."""
    try:
        payload = json.dumps({
            "model": "openai",
            "messages": [{"role": "system", "content": system[:5000]},
                         {"role": "user", "content": user[:5000]}],
            "max_tokens": max_tokens,
            "reasoning_effort": "low",
        }).encode()
        req = urllib.request.Request("https://text.pollinations.ai/openai",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        return data["choices"][0]["message"].get("content") or "Error"
    except Exception as e:
        return f"Error: {e}"

def tg_send(chat_id, text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text[:4000]}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try: urllib.request.urlopen(req, timeout=30)
    except: pass

def handle(text):
    if text.startswith("/"):
        cmd = text[1:].split(maxsplit=1)
        c = cmd[0].lower()
        a = cmd[1] if len(cmd) > 1 else ""
        if c in ("status","start"):
            return "🤖 v9.99 Bot (Render webhook 24/7)\nLLM: Pollinations GPT-OSS-20B\n\n/chat /search /status /help"
        if c == "help":
            return "Commands:\n/chat <msg> — chat\n/search <q> — Wikipedia search\n/status — status\n\nOr type any message"
        if c in ("search","find"):
            if not a: return "Usage: /search <query>"
            try:
                import urllib.parse
                q = urllib.parse.quote(a)
                url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit=3"
                req = urllib.request.Request(url, headers={"User-Agent":"Bot/1.0"})
                r = json.loads(urllib.request.urlopen(req, timeout=15).read())
                results = r.get("query",{}).get("search",[])
                return "\n".join([f"📌 {x['title']}\n   {x.get('snippet','')[:100]}" for x in results[:3]]) if results else "No results"
            except Exception as e: return f"Error: {e}"
        if c == "chat":
            if not a: return "Usage: /chat <message>"
            return llm("You are helpful. Be concise. Answer in Russian if user writes Russian.", a)
        # Unknown command → chat
        return llm("You are helpful. Be concise.", text)
    # Regular message
    return llm("You are a proactive, helpful AI. Be concise. Answer in user's language. For math, show steps.", text)

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')
        try:
            update = json.loads(body)
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat_id = msg.get("chat", {}).get("id")
            if text and str(chat_id) == str(TG_CHAT_ID):
                print(f"RECV: {text[:60]}", flush=True)
                resp = handle(text)
                tg_send(chat_id, resp)
                print(f"SENT: {resp[:60]}", flush=True)
        except Exception as e:
            print(f"ERR: {e}", flush=True)

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if self.path == "/health":
            self.wfile.write(b'{"status":"ok","version":"v9.99"}')
        else:
            self.wfile.write(b'{"bot":"v9.99","status":"running"}')

    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"Bot starting on :{PORT}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
