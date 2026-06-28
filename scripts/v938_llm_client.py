#!/usr/bin/env python3
"""
v938_llm_client.py — UNIFIED LLM CLIENT v9.38
================================================
Solves "model busy in peak hours" via 3-layer defense:
1. CACHE: hash(prompt) → response in evidence.db (eliminates repeat calls)
2. RETRY: exponential backoff (1s, 2s, 4s, 8s) on transient errors
3. FALLBACK: z-ai → Pollinations → cached (always returns something)

Usage:
    from v938_llm_client import llm_chat
    response = llm_chat("What is 2+2?", system="You are a math tutor")
    # Returns: {"content": "4", "model": "z-ai-glm4.6v", "cached": False, "attempts": 1}
    
    # Or via CLI:
    python3 v938_llm_client.py chat --prompt "What is 2+2?"
    python3 v938_llm_client.py cache-stats
    python3 v938_llm_client.py cache-clear
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

DB_PATH = "/home/z/my-project/evidence.db"
CACHE_TABLE = "llm_cache"

# Retry config
MAX_RETRIES = 4
RETRY_DELAYS = [1, 2, 4, 8]  # exponential backoff seconds

# Timeout config
ZAI_TIMEOUT = 60
POLLINATIONS_TIMEOUT = 90


def sha8(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


def cache_key(prompt, system="", model="z-ai"):
    """Generate cache key from prompt + system + model."""
    content = f"{model}|{system}|{prompt}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


# ============================================================================
# CACHE LAYER
# ============================================================================

def init_cache_db():
    """Ensure cache table exists."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS {CACHE_TABLE} (
            cache_key TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            prompt TEXT NOT NULL,
            system TEXT DEFAULT '',
            response TEXT NOT NULL,
            tokens INTEGER DEFAULT 0,
            timestamp TEXT NOT NULL,
            hit_count INTEGER DEFAULT 0
        )
    """)
    c.execute(f"CREATE INDEX IF NOT EXISTS idx_{CACHE_TABLE}_model ON {CACHE_TABLE}(model)")
    conn.commit()
    conn.close()


def cache_get(key):
    """Get cached response. Returns None if miss."""
    init_cache_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"SELECT response, tokens, model FROM {CACHE_TABLE} WHERE cache_key=?", (key,))
    row = c.fetchone()
    if row:
        # Increment hit count
        c.execute(f"UPDATE {CACHE_TABLE} SET hit_count = hit_count + 1 WHERE cache_key=?", (key,))
        conn.commit()
        conn.close()
        return {"response": row[0], "tokens": row[1], "model": row[2], "cached": True}
    conn.close()
    return None


def cache_put(key, model, prompt, system, response, tokens):
    """Store response in cache."""
    init_cache_db()
    import datetime
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"""
        INSERT OR REPLACE INTO {CACHE_TABLE} (cache_key, model, prompt, system, response, tokens, timestamp, hit_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
    """, (key, model, prompt, system, response, tokens, ts))
    conn.commit()
    conn.close()


def cache_stats():
    """Return cache statistics."""
    init_cache_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"SELECT COUNT(*), SUM(hit_count), SUM(tokens) FROM {CACHE_TABLE}")
    total, hits, tokens = c.fetchone()
    c.execute(f"SELECT model, COUNT(*) FROM {CACHE_TABLE} GROUP BY model")
    by_model = c.fetchall()
    conn.close()
    return {
        "total_entries": total or 0,
        "total_hits": hits or 0,
        "total_tokens_saved": tokens or 0,
        "by_model": {m: cnt for m, cnt in by_model},
    }


def cache_clear():
    """Clear all cache entries."""
    init_cache_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"DELETE FROM {CACHE_TABLE}")
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted


# ============================================================================
# LLM PROVIDERS
# ============================================================================

def call_zai_chat(prompt, system="", timeout=ZAI_TIMEOUT):
    """Call z-ai-web-dev-sdk chat. Returns dict or raises."""
    cmd = ["npx", "z-ai-web-dev-sdk", "chat", "--prompt", prompt]
    if system:
        cmd.extend(["--system", system])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    raw = result.stdout
    # Check for "model busy" or rate limit errors
    if "busy" in raw.lower() or "rate limit" in raw.lower() or "429" in raw:
        raise RuntimeError(f"z-ai rate limited: {raw[:200]}")
    if "error" in raw.lower() and "choices" not in raw:
        raise RuntimeError(f"z-ai error: {raw[:200]}")
    # Parse JSON
    m = re.search(r'\{\s*"choices"', raw, re.S)
    if not m:
        raise RuntimeError(f"z-ai no JSON: {raw[:200]}")
    start = m.start()
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == '{': depth += 1
        elif raw[i] == '}':
            depth -= 1
            if depth == 0:
                obj = json.loads(raw[start:i+1])
                return {
                    "content": obj["choices"][0]["message"]["content"],
                    "tokens": obj.get("usage", {}).get("total_tokens", 0),
                    "model": obj.get("model", "glm-4-plus"),
                }
    raise RuntimeError("z-ai incomplete JSON")


def call_pollinations_chat(prompt, system="", timeout=POLLINATIONS_TIMEOUT):
    """Call Pollinations.AI free LLM (gpt-oss-20b). No auth."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    payload = json.dumps({
        "model": "openai",
        "messages": messages,
        "max_tokens": 1000,
    }).encode("utf-8")
    
    req = urllib.request.Request(
        "https://text.pollinations.ai/openai",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    raw = resp.read().decode("utf-8")
    obj = json.loads(raw)
    return {
        "content": obj["choices"][0]["message"]["content"],
        "tokens": obj.get("usage", {}).get("total_tokens", 0),
        "model": obj.get("model", "gpt-oss-20b"),
    }


# ============================================================================
# UNIFIED LLM CHAT (cache + retry + fallback)
# ============================================================================

def llm_chat(prompt, system="", prefer_cache=True, verbose=False):
    """
    Unified LLM chat with caching, retry, and fallback.
    
    Returns:
        {
            "content": str,
            "model": str,
            "tokens": int,
            "cached": bool,
            "attempts": int,
            "provider_chain": [list of providers tried]
        }
    """
    init_cache_db()
    provider_chain = []
    attempts = 0
    
    # Layer 1: CACHE
    if prefer_cache:
        key = cache_key(prompt, system, "any")
        cached = cache_get(key)
        if cached:
            if verbose:
                print(f"[cache HIT] key={key[:8]} model={cached['model']}", file=sys.stderr)
            return {
                "content": cached["response"],
                "model": cached["model"] + " (cached)",
                "tokens": 0,  # no tokens spent on cache hit
                "cached": True,
                "attempts": 0,
                "provider_chain": ["cache"],
            }
    
    # Layer 2: z-ai with retry
    for attempt in range(MAX_RETRIES):
        attempts += 1
        provider_chain.append(f"z-ai(attempt {attempt+1})")
        try:
            if verbose:
                print(f"[z-ai attempt {attempt+1}] prompt={prompt[:50]!r}...", file=sys.stderr)
            result = call_zai_chat(prompt, system)
            # Success — cache it
            key = cache_key(prompt, system, "any")
            cache_put(key, result["model"], prompt, system, result["content"], result["tokens"])
            # Also cache under z-ai-specific key
            key_zai = cache_key(prompt, system, "z-ai")
            cache_put(key_zai, result["model"], prompt, system, result["content"], result["tokens"])
            return {
                "content": result["content"],
                "model": result["model"],
                "tokens": result["tokens"],
                "cached": False,
                "attempts": attempts,
                "provider_chain": provider_chain,
            }
        except subprocess.TimeoutExpired:
            if verbose:
                print(f"[z-ai timeout] attempt {attempt+1}", file=sys.stderr)
            provider_chain.append(f"z-ai-timeout(attempt {attempt+1})")
        except Exception as e:
            if verbose:
                print(f"[z-ai error] attempt {attempt+1}: {e}", file=sys.stderr)
            provider_chain.append(f"z-ai-error(attempt {attempt+1})")
        
        # Exponential backoff (skip on last attempt)
        if attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAYS[attempt]
            if verbose:
                print(f"[backoff] {delay}s...", file=sys.stderr)
            time.sleep(delay)
    
    # Layer 3: FALLBACK to Pollinations
    attempts += 1
    provider_chain.append("pollinations")
    try:
        if verbose:
            print(f"[pollinations] fallback...", file=sys.stderr)
        result = call_pollinations_chat(prompt, system)
        # Cache it
        key = cache_key(prompt, system, "any")
        cache_put(key, result["model"], prompt, system, result["content"], result["tokens"])
        key_pol = cache_key(prompt, system, "pollinations")
        cache_put(key_pol, result["model"], prompt, system, result["content"], result["tokens"])
        return {
            "content": result["content"],
            "model": result["model"],
            "tokens": result["tokens"],
            "cached": False,
            "attempts": attempts,
            "provider_chain": provider_chain,
        }
    except Exception as e:
        if verbose:
            print(f"[pollinations error] {e}", file=sys.stderr)
        provider_chain.append(f"pollinations-error")
    
    # All providers failed — return error
    return {
        "content": "",
        "model": "none",
        "tokens": 0,
        "cached": False,
        "attempts": attempts,
        "provider_chain": provider_chain,
        "error": "all providers failed",
    }


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="v9.38 unified LLM client")
    parser.add_argument("command", choices=["chat", "cache-stats", "cache-clear", "cache-get"])
    parser.add_argument("--prompt", help="prompt for chat")
    parser.add_argument("--system", default="", help="system prompt")
    parser.add_argument("--no-cache", action="store_true", help="skip cache")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--key", help="cache key for cache-get")
    args = parser.parse_args()
    
    if args.command == "chat":
        if not args.prompt:
            print("--prompt required for chat")
            sys.exit(2)
        result = llm_chat(args.prompt, args.system, prefer_cache=not args.no_cache, verbose=args.verbose)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result.get("content") else 1)
    
    elif args.command == "cache-stats":
        stats = cache_stats()
        print(json.dumps(stats, indent=2))
    
    elif args.command == "cache-clear":
        deleted = cache_clear()
        print(f"cleared {deleted} entries")
    
    elif args.command == "cache-get":
        if not args.key:
            print("--key required")
            sys.exit(2)
        result = cache_get(args.key)
        print(json.dumps(result, indent=2, ensure_ascii=False) if result else "cache miss")


if __name__ == "__main__":
    main()
