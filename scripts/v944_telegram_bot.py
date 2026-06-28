#!/usr/bin/env python3
"""
v944_telegram_bot.py — TELEGRAM BOT for v9.43 infrastructure v9.44
===================================================================
Mobile control of v9.43 meta-prompt infrastructure via Telegram.

Commands:
    /start          — welcome + command list
    /status         — daemon + cluster + bootstrap status
    /run <gate>     — run a gate (g0_check, z3_verify, bert_check_primary_goal)
    /chat <prompt>  — LLM chat via daemon (cache + fallback)
    /audit          — show audit blockchain (last 5 blocks)
    /verify         — verify blockchain integrity
    /cost           — cost/latency dashboard summary
    /consensus <q>  — multi-model consensus (3 models vote)
    /bootstrap      — run bootstrap --check
    /alerts         — configure alert routing
    /help           — full command list

Setup:
    1. Get bot token from @BotFather
    2. Get your chat ID from @userinfobot
    3. Configure:
       python3 v944_telegram_bot.py --config --token BOT_TOKEN --chat-id YOUR_ID
    4. Start:
       python3 v944_telegram_bot.py --start

Without real token, runs in --dry-run mode (responds to stdout).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

CONFIG_FILE = "/home/z/my-project/scripts/v944_telegram_config.json"
DAEMON = "/home/z/my-project/scripts/v937_daemon.py"
LLM_CLIENT = "/home/z/my-project/scripts/v938_llm_client.py"
CLUSTER = "/home/z/my-project/scripts/v939_cluster.py"
BLOCKCHAIN = "/home/z/my-project/scripts/v943_blockchain.py"
CONSENSUS = "/home/z/my-project/scripts/v942_consensus.py"
BOOTSTRAP = "/home/z/my-project/scripts/bootstrap.sh"


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    return json.loads(Path(CONFIG_FILE).read_text())


def save_config(config):
    Path(CONFIG_FILE).write_text(json.dumps(config, indent=2))
    Path(CONFIG_FILE).chmod(0o600)


def run_daemon_cmd(cmd, args=None, timeout=120):
    """Run command via daemon."""
    try:
        cmd_args = ["--args"] + (args or [])
        result = subprocess.run(
            ["python3", DAEMON, "--run", cmd] + cmd_args,
            capture_output=True, text=True, timeout=timeout
        )
        return json.loads(result.stdout.strip())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def format_status():
    """Get infrastructure status."""
    lines = ["🤖 v9.43 Infrastructure Status\n"]
    
    # Daemon
    r = run_daemon_cmd("health", timeout=5)
    if r.get("ok"):
        result = r["result"]
        lines.append(f"✅ Daemon: ALIVE (uptime {result['uptime_sec']:.0f}s)")
        lines.append(f"   Resources: {', '.join(result['resources'])}")
    else:
        lines.append("❌ Daemon: DOWN")
    
    # Bootstrap
    try:
        result = subprocess.run(
            ["bash", BOOTSTRAP, "--check"],
            capture_output=True, text=True, timeout=30
        )
        if "bootstrap complete" in result.stdout:
            lines.append("✅ Bootstrap: all layers OK")
        else:
            lines.append("⚠️ Bootstrap: issues detected")
    except Exception:
        lines.append("❌ Bootstrap: check failed")
    
    # Cache stats
    r = run_daemon_cmd("llm_cache_stats", timeout=5)
    if r.get("ok"):
        stats = r["result"]
        lines.append(f"📦 Cache: {stats['total_entries']} entries, {stats['total_hits']} hits")
    
    return "\n".join(lines)


def format_gate_result(gate_cmd, args=None):
    """Run gate and format result."""
    r = run_daemon_cmd(gate_cmd, args)
    if not r.get("ok"):
        return f"❌ Error: {r.get('error', 'unknown')}"
    
    result = r["result"]
    if gate_cmd == "g0_check":
        status = "✅ PASS" if result.get("pass") else "❌ FAIL"
        return f"{status}\nHash: {result.get('actual_hash', '?')}"
    
    elif gate_cmd == "z3_verify":
        status = "✅ PROVEN" if result.get("proven") else "❌ FAIL"
        return f"{status}\nTime: {result.get('time_sec', '?')}s"
    
    elif gate_cmd == "bert_check_primary_goal":
        status = "✅ PASS" if result.get("pass") else "❌ FAIL"
        return f"{status}\nSimilarity: {result.get('similarity', 0):.4f}"
    
    return f"```\n{json.dumps(result, indent=2)[:500]}\n```"


def format_audit():
    """Show audit blockchain."""
    try:
        result = subprocess.run(
            ["python3", BLOCKCHAIN, "export"],
            capture_output=True, text=True, timeout=10
        )
        chain = json.loads(result.stdout)
        if not chain:
            return "📋 Audit blockchain: empty"
        
        lines = [f"📋 Audit Blockchain ({len(chain)} blocks)\n"]
        for block in chain[-5:]:  # last 5
            lines.append(f"Block {block['index']}: {block['claim'][:50]}")
            lines.append(f"  hash: {block['hash'][:16]}...")
            lines.append(f"  time: {block['timestamp']}")
            if block.get('evidence'):
                lines.append(f"  evidence: {json.dumps(block['evidence'])[:80]}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error: {e}"


def format_cost():
    """Cost dashboard summary."""
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v936_cost_dashboard.py"],
            capture_output=True, text=True, timeout=10
        )
        # Parse summary
        if "Total tokens" in result.stdout:
            return f"💰 Cost Dashboard\n\n{result.stdout}"
        return "💰 No cost data yet"
    except Exception as e:
        return f"❌ Error: {e}"


def llm_chat(prompt, system=""):
    """LLM chat via daemon."""
    r = run_daemon_cmd("llm_chat", [prompt, system], timeout=180)
    if not r.get("ok"):
        return f"❌ Error: {r.get('error')}"
    
    result = r["result"]
    content = result.get("content", "")
    model = result.get("model", "?")
    cached = result.get("cached", False)
    tokens = result.get("tokens", 0)
    
    cache_str = "📦 cached" if cached else f"🆕 {tokens} tokens"
    return f"🤖 {model} ({cache_str})\n\n{content}"


def run_consensus(prompt):
    """Multi-model consensus."""
    try:
        result = subprocess.run(
            ["python3", CONSENSUS, "--prompt", prompt, "--parallel"],
            capture_output=True, text=True, timeout=60
        )
        data = json.loads(result.stdout)
        
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
        return f"❌ Error: {e}"


# ============================================================================
# COMMAND HANDLERS
# ============================================================================

COMMANDS = {
    "start": lambda args: (
        "🤖 v9.43 Telegram Bot\n\n"
        "Commands:\n"
        "/status — infrastructure status\n"
        "/run <gate> — run gate (g0_check, z3_verify, bert_check_primary_goal)\n"
        "/chat <prompt> — LLM chat\n"
        "/audit — audit blockchain\n"
        "/verify — verify blockchain\n"
        "/cost — cost dashboard\n"
        "/consensus <question> — 3-model vote\n"
        "/bootstrap — run bootstrap check\n"
        "/help — full help"
    ),
    "help": lambda args: (
        "📚 v9.43 Bot Help\n\n"
        "Gate commands (/run):\n"
        "  g0_check — PRIMARY_GOAL hash\n"
        "  z3_verify — Z3 formal proof\n"
        "  bert_check_primary_goal — BERT semantic check\n\n"
        "LLM commands:\n"
        "  /chat <prompt> — single LLM call (cache+fallback)\n"
        "  /consensus <question> — 3 models vote\n\n"
        "Monitoring:\n"
        "  /status — daemon+cluster+bootstrap\n"
        "  /cost — tokens spent\n"
        "  /audit — blockchain log\n"
        "  /verify — blockchain integrity\n\n"
        "Admin:\n"
        "  /bootstrap — recovery check"
    ),
    "status": lambda args: format_status(),
    "run": lambda args: format_gate_result(args[0], args[1:]) if args else "Usage: /run <gate>",
    "chat": lambda args: llm_chat(" ".join(args)) if args else "Usage: /chat <prompt>",
    "audit": lambda args: format_audit(),
    "verify": lambda args: (
        subprocess.run(["python3", BLOCKCHAIN, "verify"], capture_output=True, text=True).stdout
    ),
    "cost": lambda args: format_cost(),
    "consensus": lambda args: run_consensus(" ".join(args)) if args else "Usage: /consensus <question>",
    "bootstrap": lambda args: (
        subprocess.run(["bash", BOOTSTRAP, "--check"], capture_output=True, text=True).stdout[-500:]
    ),
}


def handle_command(text):
    """Handle command text, return response."""
    if not text.startswith("/"):
        return "Send /help for commands"
    
    parts = text[1:].split()
    cmd = parts[0].lower() if parts else ""
    args = parts[1:]
    
    handler = COMMANDS.get(cmd)
    if not handler:
        return f"Unknown command: /{cmd}\nSend /help for commands"
    
    try:
        return handler(args)
    except Exception as e:
        return f"❌ Error: {e}"


# ============================================================================
# TELEGRAM BOT SERVER (requires python-telegram-bot)
# ============================================================================

def start_bot():
    """Start Telegram bot (requires real token)."""
    config = load_config()
    token = config.get("bot_token")
    chat_id = config.get("chat_id")
    
    if not token:
        print("No bot token configured. Run with --config --token TOKEN --chat-id ID")
        sys.exit(2)
    
    try:
        import urllib.request
        import urllib.parse
    except ImportError:
        sys.exit("urllib required")
    
    print(f"v9.44 Telegram bot starting...")
    print(f"Chat ID: {chat_id}")
    print(f"Polling for messages...")
    
    # Simple polling (no python-telegram-bot dependency)
    base_url = f"https://api.telegram.org/bot{token}"
    last_update_id = 0
    
    while True:
        try:
            # Get updates
            url = f"{base_url}/getUpdates?offset={last_update_id + 1}&timeout=30"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=35)
            data = json.loads(resp.read())
            
            for update in data.get("result", []):
                last_update_id = update.get("update_id", last_update_id)
                message = update.get("message", {})
                text = message.get("text", "")
                from_chat_id = str(message.get("chat", {}).get("id", ""))
                
                # Authorization: only configured chat_id
                if chat_id and from_chat_id != str(chat_id):
                    print(f"Unauthorized: chat_id={from_chat_id} (expected {chat_id})")
                    continue
                
                print(f"Received: {text[:50]}")
                
                # Handle command
                response = handle_command(text)
                
                # Send response
                send_url = f"{base_url}/sendMessage"
                payload = json.dumps({
                    "chat_id": from_chat_id,
                    "text": response[:4000],  # Telegram limit
                    "parse_mode": "Markdown",
                }).encode("utf-8")
                send_req = urllib.request.Request(
                    send_url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(send_req, timeout=10)
                print(f"Sent: {response[:50]}...")
        
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)


def dry_run():
    """Dry-run mode: read commands from stdin, print responses."""
    print("v9.44 Telegram bot DRY-RUN mode")
    print("Type commands (or /quit to exit):")
    print()
    
    while True:
        try:
            text = input("> ").strip()
            if text.lower() in ("/quit", "/exit", "quit", "exit"):
                break
            if not text:
                continue
            
            response = handle_command(text)
            print()
            print(response)
            print()
        except (EOFError, KeyboardInterrupt):
            break


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", action="store_true", help="configure bot")
    parser.add_argument("--token", help="Telegram bot token")
    parser.add_argument("--chat-id", help="authorized chat ID")
    parser.add_argument("--start", action="store_true", help="start bot")
    parser.add_argument("--dry-run", action="store_true", help="dry-run (stdin)")
    parser.add_argument("--test", metavar="CMD", help="test command without bot")
    args = parser.parse_args()
    
    if args.config:
        config = load_config()
        if args.token:
            config["bot_token"] = args.token
        if args.chat_id:
            config["chat_id"] = args.chat_id
        save_config(config)
        print(f"Config saved to {CONFIG_FILE}")
    
    elif args.test:
        response = handle_command(args.test)
        print(response)
    
    elif args.dry_run:
        dry_run()
    
    elif args.start:
        start_bot()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
