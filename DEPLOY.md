# Deploy v9.99 Bot — 3 options (all free)

## Option 1: Koyeb (RECOMMENDED — free, never sleeps)
1. Go to https://koyeb.com → Sign up with GitHub
2. Create Service → GitHub → select 9xj89gzrtw-hue/v950-bot
3. Build: Python → v948_pullbot.py
4. Set env vars:
   - TELEGRAM_BOT_TOKEN=8736969974:AAG66M9I0uGwRUksTt1iJt7v-n-f7T7BpnE
   - TELEGRAM_CHAT_ID=396449039
5. Port: 10000
6. Deploy → bot runs 24/7, NEVER sleeps

## Option 2: Render + UptimeRobot (free, keep-alive)
1. Render: https://render.com → New → Web Service → GitHub repo
2. Set env vars (same as above)
3. UptimeRobot: https://uptimerobot.com → free account
4. Add monitor: HTTP(s) → https://<render-url>.onrender.com/health
5. Interval: 5 min → Render never sleeps

## Option 3: This chat (no deployment needed)
Just talk to me here. I can:
- Send Telegram messages directly (curl api.telegram.org)
- Process any command (/search, /analyze, /code)
- Use all 110+ capabilities
- No deployment, no sleep, always works when you're here
