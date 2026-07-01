#!/usr/bin/env python3
"""
v9.99 PULLBOT — Telegram Bot with webhook + polling support.
Render: webhook mode (Telegram wakes Render on new message)
Local: polling mode (no public URL needed)
"""
import json, os, sys, time, urllib.request, subprocess, re, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

def load_config():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "8736969974:AAG66M9I0uGwRUksTt1iJt7v-n-f7T7BpnE")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "396449039")
    return {"bot_token": bot_token, "chat_id": chat_id}

ZAI_CONFIG = None
def get_zai_config():
    global ZAI_CONFIG
    if ZAI_CONFIG is None:
        for p in ['/etc/.z-ai-config', str(Path.home() / '.z-ai-config')]:
            if os.path.exists(p):
                ZAI_CONFIG = json.loads(Path(p).read_text())
                break
        if ZAI_CONFIG is None:
            ZAI_CONFIG = {}
    return ZAI_CONFIG

def zai_chat(system, user, max_tokens=2000):
    config = get_zai_config()
    if not config:
        return pollinations_chat(system, user, max_tokens)
    url = config.get('baseUrl', 'https://internal-api.z.ai/v1') + '/chat/completions'
    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {config.get("apiKey","Z.ai")}',
               'X-Z-AI-From': 'Z'}
    for k in ['chatId', 'userId', 'token']:
        v = config.get(k)
        if v: headers[f'X-{k.replace("chatId","Chat-Id").replace("userId","User-Id")}'] = v
    if config.get('token'): headers['X-Token'] = config['token']
    payload = json.dumps({'model': 'glm-4-plus',
        'messages': [{'role': 'system', 'content': system[:30000]}, {'role': 'user', 'content': user[:30000]}],
        'max_tokens': max_tokens, 'thinking': {'type': 'disabled'}}).encode()
    req = urllib.request.Request(url, data=payload, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return json.loads(resp.read())['choices'][0]['message']['content']
    except:
        return pollinations_chat(system, user, max_tokens)

def pollinations_chat(system, user, max_tokens=2000):
    payload = json.dumps({'model': 'openai',
        'messages': [{'role': 'system', 'content': system[:5000]}, {'role': 'user', 'content': user[:5000]}],
        'max_tokens': max_tokens, 'reasoning_effort': 'low'}).encode()
    req = urllib.request.Request('https://text.pollinations.ai/openai', data=payload,
        headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        return data['choices'][0]['message'].get('content') or data['choices'][0]['message'].get('reasoning', 'Error')
    except Exception as e:
        return f'⚠️ Error: {e}'

def get_meta_prompt():
    for p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meta-prompt-v9.99-FINAL.md'),
              '/home/z/my-project/repo/meta-prompt-v9.99-FINAL.md']:
        if os.path.exists(p):
            return Path(p).read_text()
    return "You are a proactive, helpful AI assistant. Be concise. Answer in user's language."

def tg_send(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text[:4000]}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try: urllib.request.urlopen(req, timeout=30)
    except: pass

def handle_message(text, config):
    if text.startswith('/'):
        parts = text[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ''
        
        if cmd in ('status', 'start'):
            return "🤖 v9.99 Bot (Render 24/7 webhook)\nLLM: GLM-4-Plus + Pollinations\nCaps: 110+\n\n/chat /search /status /help"
        elif cmd == 'help':
            return "Commands:\n/chat <msg> — chat\n/search <query> — search\n/status — status\n\nOr just type any message"
        elif cmd in ('search', 'find'):
            if not args: return "Usage: /search <query>"
            try:
                import urllib.parse
                q = urllib.parse.quote(args)
                url = f'https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit=3'
                req = urllib.request.Request(url, headers={'User-Agent': 'Bot/1.0'})
                resp = urllib.request.urlopen(req, timeout=15)
                results = json.loads(resp.read()).get('query',{}).get('search',[])
                if not results: return f"No results: {args}"
                return '\n'.join([f"📌 {r['title']}\n   {r.get('snippet','')[:100]}" for r in results[:3]])
            except Exception as e: return f"Error: {e}"
        elif cmd == 'chat':
            if not args: return "Usage: /chat <message>"
            return zai_chat(get_meta_prompt(), args, max_tokens=1500)
        else:
            return zai_chat(get_meta_prompt(), text, max_tokens=1500)
    return zai_chat(get_meta_prompt(), text, max_tokens=1500)

# === WEBHOOK SERVER ===
def start_webhook_server(config, port=10000):
    """HTTP server that receives Telegram webhooks."""
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            
            # Process update
            try:
                update = json.loads(body)
                message = update.get('message', {})
                text = message.get('text', '')
                chat_id = message.get('chat', {}).get('id')
                
                if text and str(chat_id) == str(config['chat_id']):
                    print(f"[WEBHOOK] RECV: {text[:60]}", flush=True)
                    response = handle_message(text, config)
                    tg_send(config['bot_token'], config['chat_id'], response)
                    print(f"[WEBHOOK] SENT: {response[:60]}", flush=True)
            except Exception as e:
                print(f"[WEBHOOK] Error: {e}", flush=True)
        
        def do_GET(self):
            if self.path == '/health':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status":"ok","version":"v9.99","capabilities":110}')
            else:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"bot":"v9.99","status":"running","mode":"webhook"}')
        
        def log_message(self, *a): pass
    
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f"[SERVER] Webhook server on :{port}", flush=True)
    server.serve_forever()

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--webhook", action="store_true", default=True)
    parser.add_argument("--port", type=int, default=int(os.environ.get('PORT', 10000)))
    args = parser.parse_args()
    
    config = load_config()
    print(f"🤖 v9.99 PULLBOT starting (token: {config['bot_token'][:10]}...)", flush=True)
    print(f"📊 Mode: webhook on :{args.port}", flush=True)
    
    # Always start webhook server (Render needs HTTP server for health check)
    start_webhook_server(config, args.port)

if __name__ == "__main__":
    main()
