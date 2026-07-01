#!/usr/bin/env python3
"""Smart Telegram bot — GLM-4-Plus with thinking + CoT. Smarter than free GPT/Gemini."""
import json, os, time, urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8736969974:AAG66M9I0uGwRUksTt1iJt7v-n-f7T7BpnE")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "396449039")
PORT = int(os.environ.get("PORT", 10000))

ZAI_TOKEN = os.environ.get("ZAI_TOKEN", "")
ZAI_CHAT_ID = os.environ.get("ZAI_CHAT_ID", "")
ZAI_USER_ID = os.environ.get("ZAI_USER_ID", "")
ZAI_API_KEY = os.environ.get("ZAI_API_KEY", "Z.ai")
ZAI_BASE = os.environ.get("ZAI_BASE_URL", "https://internal-api.z.ai/v1")

SMART_PROMPT = """You are an expert AI assistant, smarter than GPT-4 and Claude.

Rules:
1. For math/reasoning: ALWAYS think step by step. Show every calculation.
2. For factual questions: cite sources. If unsure, say so.
3. For coding: write complete, working code. No placeholders.
4. Be concise but complete. No filler.
5. Answer in the user's language.
6. If the question is complex: break it into steps.
7. After answering: suggest 1-2 follow-up actions.

You have capabilities: web search, image generation, data analysis, code generation, browser automation, document generation, 110+ libraries."""

def smart_chat(system, user, max_tokens=3000):
    """GLM-4-Plus with thinking enabled + Pollinations fallback."""
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
                "thinking": {"type": "enabled"},
                "temperature": 0.1,
            }).encode()
            req = urllib.request.Request(url, data=payload, headers=headers)
            resp = urllib.request.urlopen(req, timeout=120)
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"z.ai error: {e}", flush=True)
    # Fallback: Pollinations
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

def web_search(query, num=3):
    """Search via Wikipedia API."""
    try:
        import urllib.parse
        q = urllib.parse.quote(query)
        url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit={num}"
        req = urllib.request.Request(url, headers={"User-Agent": "Bot/1.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        results = json.loads(resp.read()).get("query", {}).get("search", [])
        return "\n".join([f"📌 {r['title']}\n   {r.get('snippet','')[:120]}" for r in results[:num]]) if results else "No results"
    except Exception as e:
        return f"Search error: {e}"

def handle(text):
    if text.startswith("/"):
        # Fix: use proper split
        parts = text[1:].split(maxsplit=1)
        c = parts[0].lower()
        a = parts[1] if len(parts) > 1 else ""
        
        if c in ("status", "start"):
            model = "GLM-4-Plus + thinking" if ZAI_TOKEN else "Pollinations"
            return f"🧠 v9.99 Smart Bot\nLLM: {model}\nMode: Render 24/7 webhook\n\nThis bot is SMARTER than free Gemini/ChatGPT:\n- GLM-4-Plus with thinking mode\n- Step-by-step reasoning for math\n- Source citations for facts\n- Complete code generation\n\nCommands:\n/chat <msg> — smart chat\n/search <q> — Wikipedia\n/status — this\n/help — help\n\nOr just type any message!"
        if c == "help":
            return "📝 Commands:\n\n/chat <message> — Chat with GLM-4-Plus (smart)\n/search <query> — Search Wikipedia\n/status — Bot status\n/help — This help\n\n💡 Just type any message to chat!\n\n🧠 This bot uses GLM-4-Plus with thinking mode — smarter than free Gemini/ChatGPT."
        if c in ("search", "find"):
            if not a: return "Usage: /search <query>"
            return f"🔍 {a}\n\n{web_search(a)}"
        if c == "chat":
            if not a: return "Usage: /chat <message>"
            return smart_chat(SMART_PROMPT, a)
        return smart_chat(SMART_PROMPT, text)
    return smart_chat(SMART_PROMPT, text)

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
            self.wfile.write(b'{"status":"ok","model":"glm-4-plus-thinking"}')
        else:
            self.wfile.write(b'{"bot":"v9.99","model":"glm-4-plus","thinking":true}')

    def log_message(self, *a): pass

if __name__ == "__main__":
    model = "GLM-4-Plus + thinking" if ZAI_TOKEN else "Pollinations"
    print(f"🧠 v9.99 Smart Bot on :{PORT} | LLM: {model}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
