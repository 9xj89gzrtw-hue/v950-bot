#!/usr/bin/env python3
"""Fast smart bot — single GLM-4-Plus call (2s) for webhook compatibility."""
import json, os, time, urllib.request, re
from http.server import HTTPServer, BaseHTTPRequestHandler

TG_TOKEN = "8736969974:AAG66M9I0uGwRUksTt1iJt7v-n-f7T7BpnE"
TG_CHAT_ID = "396449039"
PORT = int(os.environ.get("PORT", 10000))
ZAI_BASE = "https://internal-api.z.ai/v1"
ZAI_API_KEY = "Z.ai"
ZAI_CHAT_ID = "chat-003aef41-da9c-4de2-9852-6f1cb0c1a86c"
ZAI_USER_ID = "cee04f1b-be6c-4a0d-bd46-e72403f98ca0"
ZAI_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiY2VlMDRmMWItYmU2Yy00YTBkLWJkNDYtZTcyNDAzZjk4Y2EwIiwiY2hhdF9pZCI6ImNoYXQtMDAzYWVmNDEtZGE5Yy00ZGUyLTk4NTItNmYxY2IwYzFhODZjIiwicGxhdGZvcm0iOiJ6YWkifQ.rwxeBszZRqRvSN92ovhPLzsBALBdNE0Q03OdzwtwIIA"

PROMPT = """You are GLM-4-Plus, an expert AI assistant. Smarter than GPT-4 and Claude.
Rules: Show math steps. Cite sources. Complete code. Answer in user's language. Be concise.
NEVER say you are ChatGPT or GPT. You are GLM-4-Plus by Zhipu AI.
After answering, suggest 1 follow-up action."""

def zai(system, user, max_tokens=2000):
    """Single fast GLM-4-Plus call (~2-5s)."""
    url = ZAI_BASE + "/chat/completions"
    headers = {"Content-Type":"application/json","Authorization":f"Bearer {ZAI_API_KEY}",
        "X-Z-AI-From":"Z","X-Chat-Id":ZAI_CHAT_ID,"X-User-Id":ZAI_USER_ID,"X-Token":ZAI_TOKEN}
    payload = json.dumps({"model":"glm-4-plus",
        "messages":[{"role":"system","content":system[:30000]},{"role":"user","content":user[:30000]}],
        "max_tokens":max_tokens,"thinking":{"type":"enabled"},"temperature":0.2}).encode()
    req = urllib.request.Request(url, data=payload, headers=headers)
    resp = urllib.request.urlopen(req, timeout=50)
    return json.loads(resp.read())["choices"][0]["message"]["content"]

def pollinations(system, user, max_tokens=2000):
    payload = json.dumps({"model":"openai",
        "messages":[{"role":"system","content":system[:5000]},{"role":"user","content":user[:5000]}],
        "max_tokens":max_tokens,"reasoning_effort":"low"}).encode()
    req = urllib.request.Request("https://text.pollinations.ai/openai",data=payload,
        headers={"Content-Type":"application/json","User-Agent":"Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())["choices"][0]["message"].get("content","Error")

def smart(system, user):
    try: return zai(system, user)
    except:
        try: return pollinations(system, user)
        except Exception as e: return f"Error: {e}"

def handle(text):
    if text.startswith("/"):
        parts = text[1:].split(maxsplit=1)
        c = parts[0].lower()
        a = parts[1] if len(parts)>1 else ""
        if c in ("status","start"):
            return "🧠 GLM-4-Plus Bot (thinking mode)\n\nSmarter than free GPT/Gemini.\n\nCommands:\n/chat <msg>\n/search <q>\n/status\n/help\n\nOr just type any message!"
        if c == "help":
            return "📝 /chat <msg> — smart chat\n/search <q> — Wikipedia\n/status — status\n\n💡 Just type any message!"
        if c in ("search","find"):
            if not a: return "Usage: /search <query>"
            try:
                import urllib.parse
                q=urllib.parse.quote(a)
                url=f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit=3"
                req=urllib.request.Request(url,headers={"User-Agent":"Bot/1.0"})
                r=json.loads(urllib.request.urlopen(req,timeout=10).read())
                results=r.get("query",{}).get("search",[])
                return "\n".join([f"📌 {x['title']}\n   {x.get('snippet','')[:120]}" for x in results[:3]]) if results else "No results"
            except Exception as e: return f"Error: {e}"
        if c == "chat":
            if not a: return "Usage: /chat <message>"
            return smart(PROMPT, a)
        return smart(PROMPT, text)
    return smart(PROMPT, text)

def tg_send(chat_id, text):
    url=f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload=json.dumps({"chat_id":chat_id,"text":text[:4000]}).encode()
    req=urllib.request.Request(url,data=payload,headers={"Content-Type":"application/json"})
    try: urllib.request.urlopen(req,timeout=10)
    except: pass

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        l=int(self.headers.get("Content-Length",0))
        body=self.rfile.read(l)
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')
        try:
            u=json.loads(body)
            m=u.get("message",{})
            t=m.get("text","")
            c=m.get("chat",{}).get("id")
            if t and str(c)==str(TG_CHAT_ID):
                print(f"RECV: {t[:50]}",flush=True)
                r=handle(t)
                tg_send(c,r)
                print(f"SENT: {r[:50]}",flush=True)
        except Exception as e:
            print(f"ERR: {e}",flush=True)
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok","model":"glm-4-plus"}' if self.path=="/health" else b'{"bot":"v9.99"}')
    def log_message(self,*a): pass

if __name__=="__main__":
    print(f"🧠 Bot on :{PORT} | GLM-4-Plus + thinking",flush=True)
    HTTPServer(("0.0.0.0",PORT),H).serve_forever()
