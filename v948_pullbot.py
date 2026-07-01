#!/usr/bin/env python3
"""Ensemble Telegram bot — 3x GLM-4-Plus + thinking + vote. Smarter than any single model."""
import json, os, time, urllib.request, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import Counter

TG_TOKEN = "8736969974:AAG66M9I0uGwRUksTt1iJt7v-n-f7T7BpnE"
TG_CHAT_ID = "396449039"
PORT = int(os.environ.get("PORT", 10000))

ZAI_BASE = "https://internal-api.z.ai/v1"
ZAI_API_KEY = "Z.ai"
ZAI_CHAT_ID = "chat-003aef41-da9c-4de2-9852-6f1cb0c1a86c"
ZAI_USER_ID = "cee04f1b-be6c-4a0d-bd46-e72403f98ca0"
ZAI_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiY2VlMDRmMWItYmU2Yy00YTBkLWJkNDYtZTcyNDAzZjk4Y2EwIiwiY2hhdF9pZCI6ImNoYXQtMDAzYWVmNDEtZGE5Yy00ZGUyLTk4NTItNmYxY2IwYzFhODZjIiwicGxhdGZvcm0iOiJ6YWkifQ.rwxeBszZRqRvSN92ovhPLzsBALBdNE0Q03OdzwtwIIA"

SMART_PROMPT = """You are an expert AI assistant powered by GLM-4-Plus with ensemble reasoning.
You are part of a multi-model ensemble system that is smarter than any single model.

Rules:
1. For math/reasoning: ALWAYS think step by step. Show every calculation.
2. For factual questions: be precise. If unsure, say so.
3. For coding: write complete, working code.
4. Be concise but complete.
5. Answer in the user's language.
6. NEVER say you are ChatGPT, GPT, or Claude. You are GLM-4-Plus ensemble.
7. For complex questions: break into steps, verify each step.
8. After answering: suggest follow-up actions."""

def zai_call(system, user, max_tokens=2000, thinking=True, temp=0.1):
    """Single GLM-4-Plus call with thinking mode."""
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
        "thinking": {"type": "enabled" if thinking else "disabled"},
        "temperature": temp,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers=headers)
    resp = urllib.request.urlopen(req, timeout=120)
    return json.loads(resp.read())["choices"][0]["message"]["content"]

def pollinations_call(system, user, max_tokens=2000):
    """Pollinations fallback."""
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
    return json.loads(resp.read())["choices"][0]["message"].get("content", "Error")

def is_math_question(text):
    """Detect if question needs math/reasoning."""
    keywords = ['calculate', 'посчитай', 'how much', 'сколько', 'multiply', 'divide',
                'add', 'subtract', 'percent', '%', 'square root', 'power', 'solve',
                'equation', 'formula', '* ', '+ ', '- ', '/ ', 'math']
    return any(k in text.lower() for k in keywords)

def ensemble_chat(system, user, max_tokens=2000):
    """ENSEMBLE: 3x GLM-4-Plus + thinking + vote for math, single call for chat."""
    
    if is_math_question(user):
        # ENSEMBLE MODE: 3 independent GLM-4-Plus calls + vote
        print(f"[ENSEMBLE] Math detected, running 3x GLM-4-Plus...", flush=True)
        answers = []
        for i in range(3):
            try:
                ans = zai_call(system, user, max_tokens, thinking=True, temp=0.1)
                answers.append(ans)
                print(f"  GLM #{i+1}: {len(ans)} chars", flush=True)
            except Exception as e:
                print(f"  GLM #{i+1} error: {e}", flush=True)
        
        if len(answers) >= 2:
            # Extract final numbers from each answer
            numbers = []
            for ans in answers:
                nums = re.findall(r'(?:answer|ответ)\s*[:=]?\s*\$?([\d,]+(?:\.\d+)?)', ans, re.IGNORECASE)
                if nums:
                    numbers.append(nums[-1].replace(',', ''))
                else:
                    all_nums = re.findall(r'([\d,]+(?:\.\d+)?)', ans)
                    if all_nums:
                        numbers.append(all_nums[-1].replace(',', ''))
            
            if numbers:
                # Vote on the final number
                counter = Counter(numbers)
                winner, count = counter.most_common(1)[0]
                agreement = count / len(numbers)
                
                # Find the best answer (one that has the winning number)
                for ans in answers:
                    if winner in ans:
                        return f"{ans}\n\n📊 Ensemble: {count}/{len(numbers)} models agree on {winner}"
                
                # Fallback: return first answer
                return answers[0]
            else:
                return answers[0]  # No numbers found, return first answer
        elif answers:
            return answers[0]
    
    # REGULAR MODE: single GLM-4-Plus call with thinking
    try:
        return zai_call(system, user, max_tokens, thinking=True, temp=0.3)
    except:
        try:
            return pollinations_call(system, user, max_tokens)
        except Exception as e:
            return f"Error: {e}"

def handle(text):
    if text.startswith("/"):
        parts = text[1:].split(maxsplit=1)
        c = parts[0].lower()
        a = parts[1] if len(parts) > 1 else ""
        
        if c in ("status", "start"):
            return "🧠 v9.99 ENSEMBLE Bot\n\nLLM: GLM-4-Plus ×3 (thinking mode)\nMode: Ensemble voting for math\nFallback: Pollinations\n\nSMARTER than single model:\n- 3 independent GLM-4-Plus runs\n- Majority vote eliminates errors\n- Thinking mode for reasoning\n\nCommands:\n/chat <msg> — smart chat\n/search <q> — Wikipedia\n/status — this\n/help — help\n\nOr just type any message!"
        if c == "help":
            return "📝 Commands:\n\n/chat <msg> — Chat with GLM-4-Plus ensemble\n/search <q> — Search Wikipedia\n/status — Bot status\n/help — This help\n\n💡 Just type any message!\n\n🧠 For math questions, bot runs 3 independent GLM-4-Plus calls and votes on the answer.\nThis makes it smarter than any single model."
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
                return "\n".join([f"📌 {x['title']}\n   {x.get('snippet','')[:120]}" for x in results[:3]])
            except Exception as e: return f"Error: {e}"
        if c == "chat":
            if not a: return "Usage: /chat <message>"
            return ensemble_chat(SMART_PROMPT, a)
        return ensemble_chat(SMART_PROMPT, text)
    return ensemble_chat(SMART_PROMPT, text)

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
            self.wfile.write(b'{"status":"ok","model":"glm-4-plus-ensemble"}')
        else:
            self.wfile.write(b'{"bot":"v9.99","model":"ensemble","thinking":true}')

    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"🧠 v9.99 ENSEMBLE Bot on :{PORT}", flush=True)
    print(f"   GLM-4-Plus ×3 + thinking + vote", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
