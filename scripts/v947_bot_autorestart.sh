#!/usr/bin/env bash
# v947_bot_autorestart.sh — auto-restart wrapper for Telegram bot
set -uo pipefail
LOG="/tmp/v947_telegram_bot.log"
BOT="/home/z/my-project/scripts/v944_telegram_bot.py"

echo "[$(date -u)] Auto-restart wrapper starting..." > "$LOG"

MAX_RESTARTS=50
RESTART_COUNT=0
RESTART_DELAY=5

while [ $RESTART_COUNT -lt $MAX_RESTARTS ]; do
    echo "[$(date -u)] Starting bot (attempt $((RESTART_COUNT+1))/$MAX_RESTARTS)..." >> "$LOG"
    
    # Run bot
    python3 "$BOT" --start >> "$LOG" 2>&1
    EXIT_CODE=$?
    
    echo "[$(date -u)] Bot exited with code $EXIT_CODE" >> "$LOG"
    
    RESTART_COUNT=$((RESTART_COUNT + 1))
    
    if [ $RESTART_COUNT -lt $MAX_RESTARTS ]; then
        echo "[$(date -u)] Restarting in ${RESTART_DELAY}s..." >> "$LOG"
        sleep $RESTART_DELAY
    fi
done

echo "[$(date -u)] Max restarts ($MAX_RESTARTS) reached, giving up." >> "$LOG"
