#!/usr/bin/env python3
"""Telegram Bot + Chat API on Alibaba Cloud FC port 81."""
import json, os, sys, urllib.request
from pathlib import Path
sys.path.insert(0, '/home/z/my-project/scripts')
from fastapi import FastAPI, Request
from zai_direct import chat as zai_chat

META_PROMPT = Path('/home/z/my-project/repo/meta-prompt-v9.99-FINAL.md').read_text()
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok", "capabilities": 79, "version": "v9.99"}

@app.get("/")
async def root():
    return {"name": "v9.99 Bot", "endpoints": ["/health", "/chat", "/webhook", "/status"]}

@app.post("/chat")
async def chat_endpoint(request: Request):
    try:
        data = await request.json()
        msg = data.get('message', '')
        if not msg: return {"error": "No message"}
        r = zai_chat(META_PROMPT, msg, max_tokens=2000)
        return {"response": r.get('content', ''), "provider": r.get('provider', ''), "success": r.get('success', False)}
    except Exception as e:
        return {"error": str(e)}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        msg = data.get('message', {})
        chat_id = msg.get('chat', {}).get('id')
        text = msg.get('text', '')
        if not text or not chat_id or not TELEGRAM_TOKEN:
            return {"ok": True}
        r = zai_chat(META_PROMPT, text, max_tokens=2000)
        reply = r.get('content', 'Error') if r.get('success') else f"Error: {r.get('error')}"
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = json.dumps({'chat_id': chat_id, 'text': reply}).encode()
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        try: urllib.request.urlopen(req, timeout=30)
        except: pass
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/status")
async def status():
    return {"version": "v9.99", "capabilities": 79}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get('FC_CUSTOM_LISTEN_PORT', '81'))
    print(f"Starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
