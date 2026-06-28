# v9.50 Telegram Bot — Dockerfile
# Self-contained: Python 3.12 + all dependencies + bot code
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install z-ai-web-dev-sdk (for LLM calls)
RUN npm install -g z-ai-web-dev-sdk 2>/dev/null || true

# Install Python dependencies
RUN pip install --no-cache-dir \
    sentence-transformers \
    torch --index-url https://download.pytorch.org/whl/cpu \
    transformers \
    tokenizers \
    z3-solver \
    gensim \
    scikit-learn \
    numpy \
    cryptography \
    websockets

# Copy bot code
COPY v948_pullbot.py /app/
COPY v944_telegram_config.json /app/

# Create state directory
RUN mkdir -p /app/state /app/data

# Environment
ENV PYTHONUNBUFFERED=1
ENV TZ=UTC

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python3 -c "import json; json.load(open('/app/v944_telegram_config.json'))" || exit 1

# Run bot in loop mode (polls every 10s)
CMD ["python3", "v948_pullbot.py", "--loop", "--interval", "10"]
