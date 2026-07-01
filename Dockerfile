FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git jq ffmpeg pandoc libreoffice tesseract-ocr \
    qpdf ghostscript antiword \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js + z-ai SDK
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g z-ai-web-dev-sdk agent-browser \
    && agent-browser install || true

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browsers
RUN playwright install chromium --with-deps || true

# Copy bot
COPY v948_pullbot.py .
COPY deploy/v944_telegram_config.json .

# Health check endpoint built into bot
EXPOSE 10000

CMD ["python", "v948_pullbot.py", "--loop", "--interval", "5"]
