#!/usr/bin/env python3
"""
v948_bot.py — TELEGRAM BOT v9.48 (simplified, robust)
=======================================================
Rewritten for reliability:
1. No daemon dependency for /status, /help, /audit (direct subprocess)
2. /chat uses direct LLM call (not daemon)
3. Catches ALL exceptions
4. Sends error messages to user (never silent fail)
5. Auto-restarts on crash (built-in, not external wrapper)
6. 60s polling timeout (Telegram long-polling)

Usage:
    python3 v948_bot.py --start
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


def log(msg):
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        Path("/tmp/v948_bot.log").write_text(
            Path("/tmp/v948_bot.log").read_text() + line + "\n" if Path("/tmp/v948_bot.log").exists() else line + "\n"
        )
    except:
        pass


def load_config():
    return json.loads(Path(CONFIG_FILE).read_text())


def tg_send(token, chat_id, text):
    """Send message to Telegram. Splits long messages."""
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


def tg_typing(token, chat_id):
    """Send typing indicator."""
    url = f"https://api.telegram.org/bot{token}/sendChatAction"
    payload = json.dumps({"chat_id": chat_id, "action": "typing"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=5)
    except:
        pass


# ============================================================================
# COMMAND HANDLERS (all catch exceptions, never crash bot)
# ============================================================================

def cmd_start(args, config):
    return ("🤖 v9.48 Telegram Bot\n\n"
            "Commands:\n"
            "/status — infrastructure status\n"
            "/help — all commands\n"
            "/chat <text> — LLM chat\n"
            "/consensus <question> — 3-model vote\n"
            "/audit — audit blockchain\n"
            "/verify — verify blockchain\n"
            "/gates — run all gates\n"
            "/redteam — run red team\n"
            "/cost — cost stats")


def cmd_help(args, config):
    return cmd_start(args, config)


def cmd_status(args, config):
    """Infrastructure status — direct, no daemon needed."""
    lines = ["🤖 v9.48 Infrastructure Status\n"]
    
    # Check daemon
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v937_daemon.py", "--status"],
            capture_output=True, text=True, timeout=10
        )
        if "ALIVE" in result.stdout:
            lines.append("✅ Daemon: ALIVE")
            # Extract uptime
            for line in result.stdout.split("\n"):
                if "uptime" in line:
                    lines.append(f"   {line.strip()}")
                if "resources" in line:
                    lines.append(f"   {line.strip()}")
        else:
            lines.append("❌ Daemon: DOWN")
    except Exception as e:
        lines.append(f"❌ Daemon: error ({e})")
    
    # Check git
    try:
        result = subprocess.run(["git", "-C", "/home/z/my-project", "log", "--oneline", "-1"],
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines.append(f"📝 Git: {result.stdout.strip()}")
    except:
        pass
    
    # Check disk
    try:
        result = subprocess.run(["df", "-h", "/home/z"], capture_output=True, text=True, timeout=5)
        lines.append(f"💾 Disk: {result.stdout.strip().split(chr(10))[-1]}")
    except:
        pass
    
    # Check output.md
    output_md = Path("/home/z/my-project/download/output.md")
    lines.append(f"📄 output.md: {'exists' if output_md.exists() else 'MISSING'}")
    
    return "\n".join(lines)


def cmd_chat(args, config):
    """LLM chat — direct call, no daemon."""
    if not args:
        return "Usage: /chat <your message>"
    
    prompt = " ".join(args)
    
    # Try z-ai SDK directly
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
                        tokens = obj.get("usage", {}).get("total_tokens", 0)
                        return f"🤖 {model} ({tokens} tokens)\n\n{content}"
    except subprocess.TimeoutExpired:
        pass  # try fallback
    except Exception as e:
        log(f"z-ai error: {e}")
    
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
        model = data.get("model", "gpt-oss-20b")
        return f"🤖 {model} (Pollinations fallback)\n\n{content}"
    except Exception as e:
        return f"❌ LLM error: {e}\n\nBoth z-ai and Pollinations failed. Try again later."


def cmd_consensus(args, config):
    """3-model consensus."""
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
        
        lines = [f"{emoji} Consensus: {confidence} ({agreement})\n"]
        lines.append(f"Answer: {answer}\n")
        lines.append("Models:")
        for model, ans in data.get("model_answers", {}).items():
            lines.append(f"  {model}: {ans[:60]}")
        
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Consensus error: {e}"


def cmd_audit(args, config):
    """Show audit blockchain."""
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v943_blockchain.py", "status"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout or "No blockchain"
    except Exception as e:
        return f"❌ Audit error: {e}"


def cmd_verify(args, config):
    """Verify blockchain."""
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v943_blockchain.py", "verify"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout or "No blockchain"
    except Exception as e:
        return f"❌ Verify error: {e}"


def cmd_gates(args, config):
    """Run all gates."""
    lines = ["🧪 Running gates...\n"]
    
    # G0
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/g0_check.py"],
            capture_output=True, text=True, timeout=10
        )
        lines.append(f"G0: {'✅' if result.returncode == 0 else '⚠️'} (exit {result.returncode})")
    except Exception as e:
        lines.append(f"G0: ❌ {e}")
    
    # Z3
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v928_z3_formal_verify.py"],
            capture_output=True, text=True, timeout=60
        )
        proven = "UNSAT" in result.stdout and "PROVEN" in result.stdout
        lines.append(f"Z3: {'✅ PROVEN' if proven else '⚠️'}")
    except Exception as e:
        lines.append(f"Z3: ❌ {e}")
    
    # Red team
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v946_redteam.py", "run"],
            capture_output=True, text=True, timeout=120
        )
        # Extract block rate
        import re
        m = re.search(r'Blocked: (\d+) \((\d+\.?\d*)%\)', result.stdout)
        if m:
            lines.append(f"Red Team: ✅ {m.group(1)} blocked ({m.group(2)}%)")
        else:
            lines.append(f"Red Team: ⚠️ ran but couldn't parse result")
    except Exception as e:
        lines.append(f"Red Team: ❌ {e}")
    
    return "\n".join(lines)


def cmd_redteam(args, config):
    """Run red team."""
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v946_redteam.py", "run"],
            capture_output=True, text=True, timeout=120
        )
        # Parse summary
        output = result.stdout
        # Extract last 15 lines
        lines = output.strip().split("\n")[-15:]
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Red team error: {e}"


def cmd_cost(args, config):
    """Cost stats."""
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v938_llm_client.py", "cache-stats"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout or "No cache stats"
    except Exception as e:
        return f"❌ Cost error: {e}"


COMMANDS = {
    "start": cmd_start,
    "help": cmd_help,
    "status": cmd_status,
    "chat": cmd_chat,
    "consensus": cmd_consensus,
    "audit": cmd_audit,
    "verify": cmd_verify,
    "gates": cmd_gates,
    "redteam": cmd_redteam,
    "cost": cmd_cost,
}


def handle_message(text, config):
    """Handle incoming message. NEVER raises."""
    try:
        if not text.startswith("/"):
            return "Send /help for commands"
        
        parts = text[1:].split()
        cmd = parts[0].lower() if parts else ""
        args = parts[1:]
        
        handler = COMMANDS.get(cmd)
        if not handler:
            return f"Unknown: /{cmd}\nSend /help"
        
        return handler(args, config)
    except Exception as e:
        log(f"HANDLE ERROR: {e}\n{traceback.format_exc()}")
        return f"❌ Error: {e}"


# ============================================================================
# BOT LOOP (with auto-restart built in)
# ============================================================================

def run_bot():
    config = load_config()
    token = config["bot_token"]
    chat_id = str(config["chat_id"])
    
    log("v9.48 bot starting...")
    log(f"Chat ID: {chat_id}")
    
    base_url = f"https://api.telegram.org/bot{token}"
    last_update_id = 0
    
    # Send startup notification
    tg_send(token, chat_id, "✅ v9.48 bot started!\n\nSend /status to check infrastructure.\nSend /help for all commands.")
    
    while True:
        try:
            # Long-polling (60s timeout)
            url = f"{base_url}/getUpdates?offset={last_update_id + 1}&timeout=60"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=65)
            data = json.loads(resp.read())
            
            for update in data.get("result", []):
                last_update_id = update.get("update_id", last_update_id)
                message = update.get("message", {})
                text = message.get("text", "")
                from_chat_id = str(message.get("chat", {}).get("id", ""))
                
                # Auth check
                if from_chat_id != chat_id:
                    log(f"Unauthorized: {from_chat_id}")
                    continue
                
                log(f"RECEIVED: {text[:80]}")
                
                # Typing indicator
                tg_typing(token, from_chat_id)
                
                # Handle (never raises)
                response = handle_message(text, config)
                
                # Send response
                tg_send(token, from_chat_id, response)
                log(f"SENT: {response[:80]}")
        
        except urllib.error.URLError as e:
            log(f"Network error: {e}, retrying in 5s...")
            time.sleep(5)
        except Exception as e:
            log(f"LOOP ERROR: {e}\n{traceback.format_exc()}")
            log("Restarting loop in 5s...")
            time.sleep(5)


def simulate_command(command):
    """Simulate a command (for testing without Telegram)."""
    config = load_config()
    response = handle_message(command, config)
    return response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--simulate", metavar="CMD", help="simulate command locally")
    args = parser.parse_args()
    
    if args.simulate:
        response = simulate_command(args.simulate)
        print(response)
    elif args.start:
        # Clear old log
        Path("/tmp/v948_bot.log").write_text("")
        run_bot()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
