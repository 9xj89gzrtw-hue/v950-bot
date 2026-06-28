#!/usr/bin/env python3
"""
v942_webhooks.py — ALERTING WEBHOOKS v9.42
============================================
Send alerts to Slack/Telegram when gates fail or critical events occur.

Supports:
- Slack incoming webhooks (https://hooks.slack.com/services/...)
- Telegram bot API (https://api.telegram.org/bot<token>/sendMessage)
- Generic HTTP POST webhook
- Local file logging (fallback)

Alert levels:
- critical: Z3 proof failed, daemon down, BERT missing
- warning: high failure rate, low cache hit, high latency
- info: workers at max, cluster restart

Usage:
    # Configure:
    python3 v942_webhooks.py --configure slack --url https://hooks.slack.com/services/...
    python3 v942_webhooks.py --configure telegram --token 123456:ABC --chat-id 789
    
    # Send alert:
    python3 v942_webhooks.py --send --level critical --title "Z3 Proof Failed" --message "..."
    
    # As module:
    from v942_webhooks import send_alert
    send_alert("critical", "Daemon Down", "Daemon PID 12345 not responding")
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

CONFIG_FILE = "/home/z/my-project/scripts/v942_webhook_config.json"
LOG_FILE = "/home/z/my-project/download/webhook_alerts.log"


def load_config():
    """Load webhook configuration."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        return json.loads(Path(CONFIG_FILE).read_text())
    except Exception:
        return {}


def save_config(config):
    """Save webhook configuration."""
    Path(CONFIG_FILE).write_text(json.dumps(config, indent=2))
    Path(CONFIG_FILE).chmod(0o600)


def log_to_file(level, title, message):
    """Fallback: log alert to file."""
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entry = f"[{ts}] [{level.upper()}] {title}: {message}\n"
    with open(LOG_FILE, "a") as f:
        f.write(entry)


def send_slack(webhook_url, level, title, message):
    """Send alert to Slack."""
    emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(level, "📝")
    color = {"critical": "danger", "warning": "warning", "info": "good"}.get(level, "#439FE0")
    
    payload = {
        "attachments": [{
            "color": color,
            "title": f"{emoji} {title}",
            "text": message,
            "footer": "v9.42 meta-prompt",
            "ts": int(time.time()),
        }]
    }
    
    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status == 200
    except Exception as e:
        print(f"Slack error: {e}", file=sys.stderr)
        return False


def send_telegram(bot_token, chat_id, level, title, message):
    """Send alert to Telegram."""
    emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(level, "📝")
    text = f"{emoji} *{title}*\n\n{message}\n\n_v9.42 meta-prompt_"
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return result.get("ok", False)
    except Exception as e:
        print(f"Telegram error: {e}", file=sys.stderr)
        return False


def send_alert(level, title, message, verbose=False):
    """Send alert to all configured webhooks."""
    config = load_config()
    sent = []
    
    # Slack
    if "slack" in config and config["slack"].get("url"):
        if verbose:
            print(f"[webhook] sending to Slack...", file=sys.stderr)
        if send_slack(config["slack"]["url"], level, title, message):
            sent.append("slack")
    
    # Telegram
    if "telegram" in config and config["telegram"].get("bot_token"):
        if verbose:
            print(f"[webhook] sending to Telegram...", file=sys.stderr)
        if send_telegram(
            config["telegram"]["bot_token"],
            config["telegram"]["chat_id"],
            level, title, message
        ):
            sent.append("telegram")
    
    # Always log to file as fallback
    log_to_file(level, title, message)
    sent.append("file")
    
    return sent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--configure", choices=["slack", "telegram"], help="configure webhook")
    parser.add_argument("--url", help="Slack webhook URL")
    parser.add_argument("--token", help="Telegram bot token")
    parser.add_argument("--chat-id", help="Telegram chat ID")
    parser.add_argument("--send", action="store_true", help="send alert")
    parser.add_argument("--level", choices=["critical", "warning", "info"], default="info")
    parser.add_argument("--title", default="Test Alert")
    parser.add_argument("--message", default="This is a test alert from v9.42")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    
    if args.configure:
        config = load_config()
        if args.configure == "slack":
            if not args.url:
                print("--url required for slack config")
                sys.exit(2)
            config["slack"] = {"url": args.url}
            save_config(config)
            print(f"Slack webhook configured")
        
        elif args.configure == "telegram":
            if not args.token or not args.chat_id:
                print("--token and --chat-id required for telegram")
                sys.exit(2)
            config["telegram"] = {"bot_token": args.token, "chat_id": args.chat_id}
            save_config(config)
            print(f"Telegram webhook configured")
    
    elif args.send:
        sent = send_alert(args.level, args.title, args.message, verbose=args.verbose)
        print(f"Alert sent to: {', '.join(sent)}")
    
    elif args.status:
        config = load_config()
        print("Webhook configuration:")
        print(json.dumps({k: {kk: ('***' if 'token' in kk or 'url' in kk else vv) for kk, vv in v.items()} for k, v in config.items()}, indent=2))
        print(f"\nLog file: {LOG_FILE}")
        if os.path.exists(LOG_FILE):
            lines = Path(LOG_FILE).read_text().strip().split("\n")
            print(f"Log entries: {len(lines)}")
            if lines:
                print(f"Last entry: {lines[-1]}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
