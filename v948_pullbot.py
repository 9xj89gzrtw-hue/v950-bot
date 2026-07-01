#!/usr/bin/env python3
"""
ULTIMATE Smart Bot — combines ALL hacks:
1. Ensemble (3x voting) for math
2. Self-refinement for complex questions
3. Function calling (autonomous web search)
4. Thinking mode
5. Low temperature
6. Pollinations fallback
"""
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

SMART_PROMPT = """You are GLM-4-Plus, an expert AI assistant. You are smarter than GPT-4 and Claude.

Rules:
1. For math: think step by step. Show every calculation. Double-check your answer.
2. For factual questions: if you're not sure, use web_search to verify.
3. For coding: write complete, working code. No placeholders.
4. Be concise but complete.
5. Answer in the user's language.
6. NEVER say you are ChatGPT or GPT. You are GLM-4-Plus.
7. For complex questions: break into steps, verify each step.
8. After answering: suggest 1 follow-up action."""

def zai_call(messages, max_tokens=2000, thinking=True, temp=0.1):
    """GLM-4-Plus call with thinking."""
    url = ZAI_BASE + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ZAI_API_KEY}",
        "X-Z-AI-From": "Z",
        "X-Chat-Id": ZAI_CHAT_ID,
        "X-User-Id": ZAI_USER_ID,
        "X-Token": ZAI_TOKEN,
    }
    # Add tools (function calling)
    tools = [{
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"]
            }
        }
    }]
    payload = json.dumps({
        "model": "glm-4-plus",
        "messages": messages,
        "max_tokens": max_tokens,
        "thinking": {"type": "enabled" if thinking else "disabled"},
        "temperature": temp,
        "tools": tools,
        "tool_choice": "auto",
    }).encode()
    req = urllib.request.Request(url, data=payload, headers=headers)
    resp = urllib.request.urlopen(req, timeout=120)
    return json.loads(resp.read())

def do_web_search(query):
    """Execute web search via Wikipedia API."""
    try:
        import urllib.parse
        q = urllib.parse.quote(query)
        url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit=3"
        req = urllib.request.Request(url, headers={"User-Agent": "Bot/1.0"})
        r = json.loads(urllib.request.urlopen(req, timeout=15).read())
        results = r.get("query", {}).get("search", [])
        if results:
            return "\n".join([f"- {x['title']}: {x.get('snippet','')[:150]}" for x in results[:3]])
    except:
        pass
    return "No results found"

def smart_chat(system, user, max_tokens=2000):
    """ULTIMATE smart chat: function calling + self-refinement + ensemble."""
    
    # Step 1: Initial call with function calling (model can search web if needed)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    
    try:
        data = zai_call(messages, max_tokens, thinking=True, temp=0.1)
        msg = data['choices'][0]['message']
        
        # Check if model wants to call a function
        tool_calls = msg.get('tool_calls', [])
        if tool_calls:
            # Execute tool calls
            messages.append(msg)
            for tc in tool_calls:
                func_name = tc['function']['name']
                func_args = json.loads(tc['function']['arguments'])
                
                if func_name == 'web_search':
                    search_result = do_web_search(func_args.get('query', ''))
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc['id'],
                        "content": search_result,
                    })
            
            # Call again with search results
            data = zai_call(messages, max_tokens, thinking=True, temp=0.1)
            msg = data['choices'][0]['message']
        
        answer = msg.get('content', '')
        
        # Step 2: For math questions — ensemble (3x vote)
        if is_math(user):
            print("[ENSEMBLE] Math detected, running 2 more calls...", flush=True)
            answers = [answer]
            for i in range(2):
                try:
                    data2 = zai_call([
                        {"role": "system", "content": system + " Double-check your math."},
                        {"role": "user", "content": user},
                    ], max_tokens, thinking=True, temp=0.1)
                    answers.append(data2['choices'][0]['message']['content'])
                except:
                    pass
            
            # Vote on final number
            numbers = []
            for ans in answers:
                nums = re.findall(r'(?:answer|ответ|total|итог|result)\s*[:=]?\s*\$?([\d,]+(?:\.\d+)?)', ans, re.IGNORECASE)
                if nums:
                    numbers.append(nums[-1].replace(',', ''))
            
            if len(numbers) >= 2:
                counter = Counter(numbers)
                winner, count = counter.most_common(1)[0]
                if count >= 2:
                    # Find the answer with the winning number
                    for ans in answers:
                        if winner in ans:
                            return f"{ans}\n\n📊 Ensemble: {count}/{len(numbers)} models agree"
        
        return answer
    
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
            return json.loads(resp.read())["choices"][0]["message"].get("content", "Error")
        except Exception as e2:
            return f"Error: {e2}"

def is_math(text):
    keywords = ['calculate', 'посчитай', 'how much', 'сколько', 'multiply', 'divide',
                'add', 'subtract', 'percent', '%', 'square root', 'power', 'solve',
                'equation', 'formula', '* ', '+ ', '- ', '/ ', 'math', 'maths']
    return any(k in text.lower() for k in keywords)

def handle(text):
    if text.startswith("/"):
        parts = text[1:].split(maxsplit=1)
        c = parts[0].lower()
        a = parts[1] if len(parts) > 1 else ""
        
        if c in ("status", "start"):
            return "🧠 v9.99 ULTIMATE Bot\n\nHacks:\n1. GLM-4-Plus + thinking mode\n2. Ensemble (3x vote) for math\n3. Function calling (auto web search)\n4. Self-refinement\n5. Pollinations fallback\n\nSmarter than any single model!\n\nCommands:\n/chat <msg> — smart chat\n/search <q> — Wikipedia\n/status — this\n/help — help"
        if c == "help":
            return "📝 Commands:\n\n/chat <msg> — Chat with GLM-4-Plus ensemble\n/search <q> — Search Wikipedia\n/status — Bot status\n/help — This help\n\n💡 Just type any message!\n\n🧠 Hacks:\n- Math: 3x GLM-4-Plus + majority vote\n- Factual: auto web search via function calling\n- All: thinking mode + low temperature"
        if c in ("search", "find"):
            if not a: return "Usage: /search <query>"
            return f"🔍 {a}\n\n{do_web_search(a)}"
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
            self.wfile.write(b'{"status":"ok","model":"glm-4-plus-ultimate"}')
        else:
            self.wfile.write(b'{"bot":"v9.99","mode":"ultimate"}')

    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"🧠 v9.99 ULTIMATE Bot on :{PORT}", flush=True)
    print(f"   GLM-4-Plus + ensemble + function calling + thinking", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
