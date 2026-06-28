#!/usr/bin/env python3
"""
v948_pullbot.py — CRON-STYLE PULL BOT v9.48
=============================================
Instead of persistent long-polling (sandbox kills it), this runs as ONE-SHOT:
1. Check Telegram for new messages (getUpdates)
2. Process each
3. Send replies
4. Exit

Run via cron every 10-30 seconds. Survives sandbox resets.

Usage:
    # One-shot (process pending messages, exit):
    python3 v948_pullbot.py
    
    # Loop mode (re-run every N seconds, with auto-restart):
    python3 v948_pullbot.py --loop --interval 15
"""
import argparse
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request
import urllib.error
from pathlib import Path

CONFIG_FILE = "/home/z/my-project/scripts/v944_telegram_config.json"
STATE_FILE = "/home/z/my-project/scripts/v948_pullbot_state.json"
LOG_FILE = "/tmp/v948_pullbot.log"


def log(msg):
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = f"[{ts}] {msg}"
    print(line, flush=True)


def load_config():
    """Load config from file OR environment variables (for cloud deploy)."""
    # Check environment variables first (Render/K8s/Docker)
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if bot_token and chat_id:
        return {"bot_token": bot_token, "chat_id": chat_id}
    
    # Fallback to config file
    return json.loads(Path(CONFIG_FILE).read_text())


def load_state():
    """Load last_update_id from state file."""
    if not os.path.exists(STATE_FILE):
        return {"last_update_id": 0}
    try:
        return json.loads(Path(STATE_FILE).read_text())
    except:
        return {"last_update_id": 0}


def save_state(state):
    Path(STATE_FILE).write_text(json.dumps(state))


def tg_send(token, chat_id, text):
    """Send message to Telegram."""
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": chunk}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=30)
        except Exception as e:
            log(f"SEND ERROR: {e}")
        time.sleep(0.2)


def tg_get_updates(token, offset, timeout=5):
    """Get updates from Telegram (short timeout for one-shot)."""
    url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout={timeout}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout + 10)
        data = json.loads(resp.read())
        if data.get("ok"):
            return data.get("result", [])
    except Exception as e:
        log(f"getUpdates error: {e}")
    return []


# ============================================================================
# COMMAND HANDLERS (same as v948_bot.py)
# ============================================================================

def cmd_status(args, config):
    lines = ["🤖 v9.48 Status\n"]
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v937_daemon.py", "--status"],
            capture_output=True, text=True, timeout=10
        )
        if "ALIVE" in result.stdout:
            lines.append("✅ Daemon: ALIVE")
            for line in result.stdout.split("\n"):
                if "uptime" in line or "resources" in line:
                    lines.append(f"   {line.strip()}")
        else:
            lines.append("⚠️ Daemon: not responding")
    except Exception as e:
        lines.append(f"❌ Daemon: {e}")
    
    try:
        result = subprocess.run(["git", "-C", "/home/z/my-project", "log", "--oneline", "-1"],
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines.append(f"📝 Git: {result.stdout.strip()[:60]}")
    except:
        pass
    
    try:
        result = subprocess.run(["df", "-h", "/home/z"], capture_output=True, text=True, timeout=5)
        lines.append(f"💾 Disk: {result.stdout.strip().split(chr(10))[-1].split()[-2]}")
    except:
        pass
    
    output_md = Path("/home/z/my-project/download/output.md")
    lines.append(f"📄 output.md: {'✅' if output_md.exists() else '❌'}")
    
    return "\n".join(lines)


def cmd_help(args, config):
    return ("📚 Commands:\n"
            "/status — infrastructure\n"
            "/chat <text> — LLM\n"
            "/consensus <q> — 3-model vote\n"
            "/audit — blockchain\n"
            "/gates — run gates\n"
            "/redteam — red team\n"
            "/cost — cache stats")


def cmd_chat(args, config):
    if not args:
        return "Usage: /chat <message>"
    prompt = " ".join(args)
    
    # Try z-ai
    try:
        result = subprocess.run(
            ["npx", "z-ai-web-dev-sdk", "chat", "--prompt", prompt],
            capture_output=True, text=True, timeout=60
        )
        import re
        m = re.search(r'\{\s*"choices"', result.stdout, re.S)
        if m:
            start = m.start()
            depth = 0
            for i in range(start, len(result.stdout)):
                if result.stdout[i] == '{': depth += 1
                elif result.stdout[i] == '}':
                    depth -= 1
                    if depth == 0:
                        obj = json.loads(result.stdout[start:i+1])
                        content = obj["choices"][0]["message"]["content"]
                        model = obj.get("model", "?")
                        return f"🤖 {model}\n\n{content}"
    except:
        pass
    
    # Fallback: Pollinations
    try:
        payload = json.dumps({
            "model": "openai",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://text.pollinations.ai/openai",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        return f"🤖 gpt-oss-20b (fallback)\n\n{content}"
    except Exception as e:
        return f"❌ LLM error: {e}"


def cmd_consensus(args, config):
    if not args:
        return "Usage: /consensus <question>"
    prompt = " ".join(args)
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v942_consensus.py", "--prompt", prompt, "--parallel"],
            capture_output=True, text=True, timeout=120
        )
        data = json.loads(result.stdout.strip())
        confidence = data.get("confidence", "?")
        agreement = data.get("agreement", "?")
        answer = data.get("answer", "?")
        emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "ABSTAIN": "🔴"}.get(confidence, "⚪")
        lines = [f"{emoji} {confidence} ({agreement})\n", f"Answer: {answer}\n", "Models:"]
        for model, ans in data.get("model_answers", {}).items():
            lines.append(f"  {model}: {ans[:50]}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ {e}"


def cmd_audit(args, config):
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v943_blockchain.py", "status"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout or "No blockchain"
    except Exception as e:
        return f"❌ {e}"


def cmd_gates(args, config):
    lines = ["🧪 Gates:\n"]
    try:
        result = subprocess.run(["python3", "/home/z/my-project/scripts/g0_check.py"],
                              capture_output=True, text=True, timeout=10)
        lines.append(f"G0: {'✅' if result.returncode == 0 else '⚠️'}")
    except Exception as e:
        lines.append(f"G0: ❌ {e}")
    
    try:
        result = subprocess.run(["python3", "/home/z/my-project/scripts/v928_z3_formal_verify.py"],
                              capture_output=True, text=True, timeout=60)
        proven = "UNSAT" in result.stdout and "PROVEN" in result.stdout
        lines.append(f"Z3: {'✅ PROVEN' if proven else '⚠️'}")
    except Exception as e:
        lines.append(f"Z3: ❌ {e}")
    
    return "\n".join(lines)


def cmd_redteam(args, config):
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v946_redteam.py", "run"],
            capture_output=True, text=True, timeout=120
        )
        lines = result.stdout.strip().split("\n")[-10:]
        return "\n".join(lines)
    except Exception as e:
        return f"❌ {e}"


def cmd_cost(args, config):
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v938_llm_client.py", "cache-stats"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout or "No stats"
    except Exception as e:
        return f"❌ {e}"


COMMANDS = {
    "start": lambda a, c: cmd_help(a, c),
    "help": cmd_help,
    "status": cmd_status,
    "chat": cmd_chat,
    "consensus": cmd_consensus,
    "audit": cmd_audit,
    "gates": cmd_gates,
    "redteam": cmd_redteam,
    "cost": cmd_cost,
}


def handle_message(text, config):
    """Handle message. NEVER raises."""
    try:
        if not text.startswith("/"):
            return "Send /help"
        parts = text[1:].split()
        cmd = parts[0].lower() if parts else ""
        args = parts[1:]
        handler = COMMANDS.get(cmd)
        if not handler:
            return f"Unknown: /{cmd}\nSend /help"
        return handler(args, config)
    except Exception as e:
        return f"❌ Error: {e}"


# ============================================================================
# ONE-SHOT PROCESSOR
# ============================================================================

def process_once(config):
    """Process all pending Telegram updates. Returns count processed."""
    token = config["bot_token"]
    chat_id = str(config["chat_id"])
    
    state = load_state()
    offset = state["last_update_id"] + 1
    
    updates = tg_get_updates(token, offset, timeout=5)
    
    if not updates:
        return 0
    
    processed = 0
    for update in updates:
        update_id = update.get("update_id", 0)
        state["last_update_id"] = max(state["last_update_id"], update_id)
        
        message = update.get("message", {})
        text = message.get("text", "")
        from_chat_id = str(message.get("chat", {}).get("id", ""))
        
        if from_chat_id != chat_id:
            log(f"Unauthorized: {from_chat_id}")
            continue
        
        if not text:
            continue
        
        log(f"RECEIVED: {text[:80]}")
        
        # Handle (never raises)
        response = handle_message(text, config)
        
        # Send reply
        tg_send(token, from_chat_id, response)
        log(f"SENT: {response[:80]}")
        
        processed += 1
    
    save_state(state)
    return processed


def run_loop(interval=15):
    """Loop mode: process every N seconds."""
    config = load_config()
    log(f"v9.48 pull-bot loop mode (interval={interval}s)")
    
    while True:
        try:
            count = process_once(config)
            if count > 0:
                log(f"Processed {count} messages")
        except Exception as e:
            log(f"LOOP ERROR: {e}")
        
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="continuous mode")
    parser.add_argument("--interval", type=int, default=15, help="seconds between polls")
    parser.add_argument("--simulate", metavar="CMD", help="simulate command")
    args = parser.parse_args()
    
    if args.simulate:
        config = load_config()
        response = handle_message(args.simulate, config)
        print(response)
    elif args.loop:
        run_loop(args.interval)
    else:
        # One-shot mode
        config = load_config()
        count = process_once(config)
        log(f"One-shot: processed {count} messages")


if __name__ == "__main__":
    main()
