#!/usr/bin/env bash
# ============================================================================
# v9.50 Telegram Bot — QUICK START (one command)
# ============================================================================
# This script deploys the bot using Docker (works on any OS with Docker).
# 
# Prerequisites:
#   - Docker installed (https://docker.com)
#   - Telegram bot token (from @BotFather)
#   - Your chat ID (from @userinfobot)
#
# Usage:
#   bash QUICK_START.sh
# ============================================================================

set -e

echo "🤖 v9.50 Telegram Bot — Quick Start"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not installed. Install from: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check token
TOKEN=$(python3 -c "import json; print(json.load(open('v944_telegram_config.json')).get('bot_token',''))" 2>/dev/null || echo "")
CHAT_ID=$(python3 -c "import json; print(json.load(open('v944_telegram_config.json')).get('chat_id',''))" 2>/dev/null || echo "")

if [ -z "$TOKEN" ] || [ -z "$CHAT_ID" ]; then
    echo "📝 Enter your Telegram bot token (from @BotFather):"
    read TOKEN
    echo "📝 Enter your chat ID (from @userinfobot):"
    read CHAT_ID
    
    # Save config
    python3 -c "
import json
json.dump({'bot_token': '$TOKEN', 'chat_id': '$CHAT_ID'}, open('v944_telegram_config.json', 'w'), indent=2)
print('✅ Config saved')
"
fi

echo ""
echo "🚀 Starting bot..."
docker-compose up -d --build

echo ""
echo "✅ Bot is running!"
echo ""
echo "📱 Open Telegram and send /status to your bot"
echo ""
echo "Commands:"
echo "  docker-compose logs -f     # view logs"
echo "  docker-compose down         # stop bot"
echo "  docker-compose restart      # restart bot"
