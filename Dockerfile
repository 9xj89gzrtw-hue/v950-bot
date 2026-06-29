FROM python:3.12-slim

WORKDIR /app

# Install Node.js for z-ai SDK
RUN apt-get update && apt-get install -y --no-install-recommends curl nodejs npm && rm -rf /var/lib/apt/lists/*
RUN npm install -g z-ai-web-dev-sdk 2>/dev/null || true

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot
COPY v948_pullbot.py .

# Run
CMD ["python", "v948_pullbot.py", "--loop", "--interval", "10"]
