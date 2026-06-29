# PUSH TO GITHUB — EXACT COMMANDS

## Step 1: Create repo on GitHub (30 seconds)

1. Go to: https://github.com/new
2. Repository name: v950-bot
3. Select: Public
4. DO NOT add README, .gitignore, or license (we have them)
5. Click: Create repository

## Step 2: Push from this sandbox (copy-paste all 3 lines)

cd /home/z/my-project
git add -A
git push -u origin main

If asked for credentials:
- Username: 9xj89gzrtw-hue
- Password: YOUR_GITHUB_PERSONAL_ACCESS_TOKEN (not your password!)
  (Get token: GitHub → Settings → Developer settings → Personal access tokens → Generate new token → check "repo" scope)

## Step 3: Deploy on Render.com (2 minutes)

1. Go to: https://render.com → Sign up with GitHub
2. Dashboard → New + → Web Service
3. Find and select: 9xj89gzrtw-hue/v950-bot
4. Render detects render.yaml automatically
5. Go to Environment tab → Add:
   Key: TELEGRAM_BOT_TOKEN  Value: 8736969974:AAG66M9I0uGwRUksTt1iJt7v-n-f7T7BpnE
   Key: TELEGRAM_CHAT_ID     Value: 396449039
6. Click: Create Web Service
7. Wait 2-3 minutes for build
8. Open Telegram → @MyGlm52_bot → send /status
9. Bot responds! 24/7!
