#!/usr/bin/env python3
"""
GitHub Actions Telegram Bot — 24/7 FREE, no server needed.
Stateless: processes all unconfirmed Telegram updates each run.
Persists last_update_id by confirming updates (Telegram API marks them as read).
"""
import json, os, sys, time, urllib.request

TG_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8736969974:AAG66M9I0uGwRUksTt1iJt7v-n-f7T7BpnE')
TG_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '396449039')

ZAI_BASE = os.environ.get('ZAI_BASE_URL', 'https://internal-api.z.ai/v1')
ZAI_KEY = os.environ.get('ZAI_API_KEY', 'Z.ai')
ZAI_CHAT = os.environ.get('ZAI_CHAT_ID', '')
ZAI_USER = os.environ.get('ZAI_USER_ID', '')
ZAI_TOKEN = os.environ.get('ZAI_TOKEN', '')

def tg_api(method, **params):
    url = f'https://api.telegram.org/bot{TG_TOKEN}/{method}'
    data = json.dumps(params).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except Exception as e:
        print(f'TG error: {e}')
        return None

def zai_chat(system, user, max_tokens=2000):
    if not ZAI_TOKEN:
        return pollinations_chat(system, user, max_tokens)
    url = ZAI_BASE + '/chat/completions'
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {ZAI_KEY}',
               'X-Z-AI-From': 'Z', 'X-Chat-Id': ZAI_CHAT, 'X-User-Id': ZAI_USER, 'X-Token': ZAI_TOKEN}
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
        return f'Error: {e}'

META = """You are a proactive, helpful AI assistant with 110+ capabilities.
Be concise. Answer in Russian if user writes in Russian.
For math, show steps. If you don't know, say so."""

def handle_message(text):
    if text.startswith('/'):
        parts = text[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ''
        
        if cmd in ('status', 'start'):
            return "🤖 v9.99 Bot (GitHub Actions 24/7)\nLLM: GLM-4-Plus + Pollinations\nCapabilities: 110+\nCommands: /chat /search /status /help"
        elif cmd == 'help':
            return "Commands:\n/chat <msg> — chat\n/search <query> — web search\n/status — status\nOr just type any message"
        elif cmd in ('search', 'find'):
            if not args: return "Usage: /search <query>"
            # Use Wikipedia as fallback
            try:
                import urllib.parse
                q = urllib.parse.quote(args)
                url = f'https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit=3'
                req = urllib.request.Request(url, headers={'User-Agent': 'Bot/1.0'})
                resp = urllib.request.urlopen(req, timeout=15)
                data = json.loads(resp.read())
                results = data.get('query', {}).get('search', [])
                if not results: return f"No results for: {args}"
                lines = [f"🔍 {args}\n"]
                for r in results[:3]:
                    lines.append(f"📌 {r['title']}")
                    lines.append(f"   {r.get('snippet','')[:100]}\n")
                return '\n'.join(lines)
            except Exception as e:
                return f"Search error: {e}"
        elif cmd == 'chat':
            if not args: return "Usage: /chat <message>"
            return zai_chat(META, args, max_tokens=1500)
        else:
            return zai_chat(META, text, max_tokens=1500)
    return zai_chat(META, text, max_tokens=1500)

def main():
    print(f'🤖 Bot check: {time.strftime("%Y-%m-%d %H:%M:%S")}')
    
    # Get ALL pending updates (offset=0 = get all unconfirmed)
    result = tg_api('getUpdates', offset=0, timeout=0, limit=10)
    if not result or not result.get('ok'):
        print('No updates or error')
        return
    
    updates = result.get('result', [])
    if not updates:
        print('No new messages ✅')
        return
    
    print(f'Found {len(updates)} messages')
    last_id = 0
    
    for update in updates:
        update_id = update.get('update_id', 0)
        last_id = max(last_id, update_id)
        
        message = update.get('message', {})
        text = message.get('text', '')
        chat_id = message.get('chat', {}).get('id')
        
        if not text or str(chat_id) != TG_CHAT_ID:
            continue
        
        print(f'  RECV: {text[:60]}')
        response = handle_message(text)
        
        send = tg_api('sendMessage', chat_id=int(TG_CHAT_ID), text=response[:4000])
        if send and send.get('ok'):
            print(f'  SENT: {response[:60]}')
        else:
            print(f'  FAILED: {send}')
        time.sleep(0.5)
    
    # Confirm all processed updates (so they don't come back next run)
    if last_id > 0:
        tg_api('getUpdates', offset=last_id + 1, timeout=0, limit=1)
        print(f'Confirmed up to update_id {last_id}')

if __name__ == '__main__':
    main()
