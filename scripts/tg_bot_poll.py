#!/usr/bin/env python3
"""
Telegram Bot — POLLING mode (no webhook, no public port needed).
Runs 24/7, polls Telegram API every 3s.
Uses z.ai direct API (GLM-4-Plus) for responses — no rate limits (SmartLLM cascade).
"""
import json, os, sys, time, urllib.request
from pathlib import Path

# Add scripts to path
sys.path.insert(0, '/home/z/my-project/scripts')

# Import z.ai direct API
config = json.load(open('/etc/.z-ai-config'))
META_PROMPT = Path('/home/z/my-project/repo/meta-prompt-v9.99-FINAL.md').read_text()
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')

def zai_chat(system, user, max_tokens=2000):
    """Direct z.ai API call."""
    url = config['baseUrl'] + '/chat/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {config["apiKey"]}',
        'X-Z-AI-From': 'Z',
        'X-Chat-Id': config['chatId'],
        'X-User-Id': config['userId'],
        'X-Token': config['token'],
    }
    payload = json.dumps({
        'model': 'glm-4-plus',
        'messages': [{'role': 'system', 'content': system[:30000]},
                     {'role': 'user', 'content': user[:30000]}],
        'max_tokens': max_tokens,
        'thinking': {'type': 'disabled'},
    }).encode()
    req = urllib.request.Request(url, data=payload, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        return data['choices'][0]['message']['content']
    except Exception as e:
        # Fallback to Pollinations
        try:
            payload2 = json.dumps({
                'model': 'openai',
                'messages': [{'role': 'system', 'content': system[:5000]},
                             {'role': 'user', 'content': user[:5000]}],
                'max_tokens': max_tokens,
                'reasoning_effort': 'low',
            }).encode()
            req2 = urllib.request.Request('https://text.pollinations.ai/openai',
                data=payload2, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
            resp2 = urllib.request.urlopen(req2, timeout=60)
            data2 = json.loads(resp2.read())
            return data2['choices'][0]['message'].get('content') or data2['choices'][0]['message'].get('reasoning', 'Error')
        except:
            return f"Error: {e}"

def send_telegram(chat_id, text):
    """Send message to Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({'chat_id': chat_id, 'text': text[:4000]}).encode()
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=10)
    except:
        pass

def get_updates(offset=None):
    """Poll Telegram for new messages."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?timeout=5"
    if offset:
        url += f"&offset={offset}"
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        return data.get('result', [])
    except:
        return []

def main():
    if not TELEGRAM_TOKEN:
        print("ERROR: Set TELEGRAM_BOT_TOKEN env var")
        print("1. Message @BotFather on Telegram")
        print("2. Create a bot: /newbot")
        print("3. Get token")
        print("4. Set: export TELEGRAM_BOT_TOKEN=your_token")
        print("5. Or add to /home/z/my-project/repo/.env")
        return
    
    print(f"Bot starting... (token: {TELEGRAM_TOKEN[:10]}...)")
    offset = None
    
    while True:
        updates = get_updates(offset)
        for update in updates:
            offset = update['update_id'] + 1
            message = update.get('message', {})
            chat_id = message.get('chat', {}).get('id')
            text = message.get('text', '')
            
            if text and chat_id:
                print(f"  Received: {text[:50]}")
                
                # Get response from GLM-4-Plus
                reply = zai_chat(META_PROMPT, text)
                print(f"  Sent: {reply[:50]}")
                
                # Send to Telegram
                send_telegram(chat_id, reply)
        
        time.sleep(1)

if __name__ == "__main__":
    main()
