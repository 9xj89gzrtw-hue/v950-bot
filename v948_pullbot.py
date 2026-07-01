#!/usr/bin/env python3
"""Smart Telegram bot — GLM-4-Plus (via z.ai) + Pollinations fallback."""
import json, os, time, urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8736969974:AAG66M9I0uGwRUksTt1iJt7v-n-f7T7BpnE")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "396449039")
PORT = int(os.environ.get("PORT", 10000))

# z.ai credentials (passed as env vars on Render)
ZAI_TOKEN = os.environ.get("ZAI_TOKEN", "")
ZAI_CHAT_ID = os.environ.get("ZAI_CHAT_ID", "")
ZAI_USER_ID = os.environ.get("ZAI_USER_ID", "")
ZAI_API_KEY = os.environ.get("ZAI_API_KEY", "Z.ai")
ZAI_BASE = os.environ.get("ZAI_BASE_URL", "https://internal-api.z.ai/v1")

def smart_chat(system, user, max_tokens=2000):
    """Try z.ai GLM-4-Plus first, fall back to Pollinations."""
    # Try z.ai
    if ZAI_TOKEN:
        try:
            url = ZAI_BASE + "/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {ZAI_API_KEY}",
                "X-Z-AI-From": "Z",
                "X-Chat-Id": ZAI_CHAT_ID,
                "X-User-Id": ZAI_USER_ID,
                "X-Token": ZAI_TOKEN,
            }
            payload = json.dumps({
                "model": "glm-4-plus",
                "messages": [
                    {"role": "system", "content": system[:30000]},
                    {"role": "user", "content": user[:30000]},
                ],
                "max_tokens": max_tokens,
                "thinking": {"type": "disabled"},
            }).encode()
            req = urllib.request.Request(url, data=payload, headers=headers)
            resp = urllib.request.urlopen(req, timeout=60)
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"z.ai error: {e}", flush=True)
    
    # Fallback: Pollinations (always works)
    try:
        payload = json.dumps({
            "model": "openai",
            "messages": [
                {"role": "system", "content": system[:5000]},
                {"role": "user", "content": user[:5000]},
            ],
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

META = """You are a proactive, smart AI assistant powered by GLM-4-Plus.
- Answer in the user's language (Russian → Russian, English → English)
- Be concise but thorough
- For math: show steps step by step
- For facts: cite sources when possible
- If you don't know: say so honestly
- Suggest next actions when helpful"""

def handle(text):
    if text.startswith("/"):
        cmd = text[1:].split(maxsplit=1)
        c = cmd[0].lower()
        a = cmd[1] if len(cmd) > 1 else ""
        
        if c in ("status", "start"):
            model = "GLM-4-Plus" if ZAI_TOKEN else "Pollinations GPT-OSS-20B"
            return f"🤖 v9.99 Smart Bot\nLLM: {model}\nMode: Render webhook 24/7\n\nCommands:\n/chat <msg> — smart chat\n/search <q> — Wikipedia search\n/status — this\n/help — help\n\nOr just type any message!"
        if c == "help":
            return "📝 Commands:\n\n/chat <message> — Chat with AI\n/search <query> — Search Wikipedia\n/status — Bot status\n/help — This help\n\n💡 Just type any message to chat with GLM-4-Plus!"
        if c in ("search", "find"):
            if not a: return "Usage: /search <query>"
            try:
                import urllib.parse
                q = urllib.parse.quote(a)
                url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit=3"
                req = urllib.request.Request(url, headers={"User-Agent": "Bot/1.0"})
                r = json.loads(urllib.request.urlopen(req, timeout=15).read())
                results = r.get("query", {}).get("search", [])
                if not results: return f"No results: {a}"
                lines = [f"🔍 {a}\n"]
                for x in results[:3]:
                    lines.append(f"📌 {x['title']}")
                    lines.append(f"   {x.get('snippet','')[:100]}\n")
                return "\n".join(lines)
            except Exception as e: return f"Error: {e}"
        if c == "chat":
            if not a: return "Usage: /chat <message>"
            return smart_chat(META, a)
        # Unknown / → chat
        return smart_chat(META, text)
    
    # Regular message → smart chat
    return smart_chat(META, text)

def tg_send(chat_id, text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text[:4000]}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try: urllib.request.urlopen(req, timeout=30)
    except: pass

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
            self.wfile.write(b'{"status":"ok","version":"v9.99","model":"glm-4-plus"}')
        else:
            self.wfile.write(b'{"bot":"v9.99","status":"running"}')

    def log_message(self, *a): pass

if __name__ == "__main__":
    model = "GLM-4-Plus" if ZAI_TOKEN else "Pollinations"
    print(f"🤖 v9.99 Bot on :{PORT} | LLM: {model}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
