# v9.50 Telegram Bot — Deploy Package

## ONE-COMMAND DEPLOY (Docker)

```bash
# 1. Download this folder to your computer
# 2. Run:
docker-compose up -d

# Bot runs 24/7. Done.
```

## Requirements
- Docker installed (https://docker.com)
- That's it. No Python, no dependencies, no config.

## What it does
- Starts Telegram bot in Docker container
- Polls Telegram every 10 seconds for new messages
- Auto-restarts on crash
- Persists state across restarts

## Commands (in Telegram)
/status — infrastructure status
/chat <text> — LLM chat
/consensus <question> — 3-model vote
/audit — audit blockchain
/gates — run gates
/help — all commands

## Stop
docker-compose down
