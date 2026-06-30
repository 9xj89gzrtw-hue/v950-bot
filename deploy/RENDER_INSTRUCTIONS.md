# v9.52 Render.com Deploy — STEP BY STEP
# ==========================================
# 5 minutes to 24/7 bot. Free tier. No credit card.

# ============================================================================
# STEP 1: Push code to GitHub (2 min)
# ============================================================================

# Option A: New repo
# 1. Go to github.com → New repository → name it "v950-bot"
# 2. Don't add README (we have one)
# 3. Copy the URL

# Option B: Use existing repo
# Just add the deploy/ + scripts/ folders

# On your computer (or in this sandbox):
cd /home/z/my-project
git init  # if not already
git add -A
git commit -m "v9.51 production deploy"
git remote add origin https://github.com/YOUR_USERNAME/v950-bot.git
git push -u origin main

# ============================================================================
# STEP 2: Deploy on Render.com (2 min)
# ============================================================================

# 1. Go to https://render.com → Sign up (free, GitHub login)
# 2. Dashboard → New + → Web Service
# 3. Connect your GitHub repo "v950-bot"
# 4. Render auto-detects render.yaml → confirm settings
# 5. Go to Environment tab → add:
#    Key: TELEGRAM_BOT_TOKEN  Value: 8736969974:AAG66M9I0uGwRUksTt1iJt7v-n-f7T7BpnE
#    Key: TELEGRAM_CHAT_ID     Value: 396449039
# 6. Click "Create Web Service"
# 7. Wait 2-3 minutes for build
# 8. Bot is live 24/7!

# ============================================================================
# STEP 3: Test (1 min)
# ============================================================================

# Open Telegram → @MyGlm52_bot → send /status
# Bot responds within 10 seconds!

# ============================================================================
# MANAGEMENT
# ============================================================================

# View logs:
# Render dashboard → your service → Logs tab

# Restart:
# Render dashboard → Manual Deploy → Deploy latest commit

# Update code:
# git push → Render auto-deploys

# Stop:
# Render dashboard → Suspend (free tier: 750h/month)

# ============================================================================
# FREE TIER LIMITS
# ============================================================================
# - 750 hours/month (enough for 24/7 if single service)
# - 512MB RAM (enough for bot, not for BERT models)
# - Auto-sleep after 15min idle (won't happen — bot polls every 10s)
# - No custom domains on free tier

# ============================================================================
# ALTERNATIVE: If Render doesn't work
# ============================================================================
# Railway.app (similar, free $5 credit/month)
# Fly.io (3 free shared-cpu VMs)
# Koyeb (free nano service)
