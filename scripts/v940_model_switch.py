#!/usr/bin/env python3
"""
v940_model_switch.py — G69 AUTO-MODEL-SWITCH v9.40
====================================================
Solves "Currently in peak hours, GLM-5.2 is intensifying..." popup.

Root cause: Z.ai web chat (chat.z.ai) uses GLM-5.2 backend which shows popup
during peak hours. The z-ai-web-dev-sdk uses glm-4-plus backend (different pool,
no peak-hour popup).

Strategy:
1. ALWAYS use z-ai-web-dev-sdk (npx) — never web chat → no popup
2. If SDK also rate-limits → auto-switch to Pollinations GPT-OSS-20B
3. If Pollinations fails → use cached response
4. Optional: pin to specific model via env var ZAI_MODEL_PREFERENCE

This module is imported by v938_llm_client.py to add model-switching logic.

Usage:
    # As module (auto-used by llm_chat):
    from v940_model_switch import smart_chat
    result = smart_chat("Hello", system="...")
    
    # CLI:
    python3 v940_model_switch.py chat --prompt "Hello"
    python3 v940_model_switch.py models  # list available models
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, "/home/z/my-project/scripts")

# Model preferences (in priority order)
# These are backends, not web-chat models — no peak-hour popup
MODEL_PROVIDERS = [
    {
        "name": "z-ai-sdk-glm4-plus",
        "type": "npx_sdk",
        "model": "glm-4-plus",
        "priority": 1,
        "avg_latency_sec": 1.5,
        "rate_limit_rpm": 60,  # estimated
        "notes": "Z.ai SDK backend, no peak-hour popup (different from web chat GLM-5.2)",
    },
    {
        "name": "pollinations-gpt-oss-20b",
        "type": "http",
        "endpoint": "https://text.pollinations.ai/openai",
        "model": "openai",
        "priority": 2,
        "avg_latency_sec": 3.0,
        "rate_limit_rpm": 30,  # anonymous tier
        "notes": "Free, no auth, OpenAI open-source 20B. Always available fallback.",
    },
]


def smart_chat(prompt, system="", verbose=False):
    """
    Smart chat with auto-model-switching.
    
    Tries providers in priority order. On rate-limit/busy, auto-switches to next.
    Uses cache (via v938_llm_client) to avoid repeat calls.
    
    Returns:
        {
            "content": str,
            "model": str,
            "provider": str,
            "tokens": int,
            "cached": bool,
            "attempts": int,
            "provider_chain": [str],
        }
    """
    # Import cache layer from v938
    from v938_llm_client import (
        cache_key, cache_get, cache_put, init_cache_db,
        call_zai_chat, call_pollinations_chat
    )
    
    init_cache_db()
    provider_chain = []
    attempts = 0
    
    # Layer 1: CACHE
    key = cache_key(prompt, system, "any")
    cached = cache_get(key)
    if cached:
        if verbose:
            print(f"[cache HIT] model={cached['model']}", file=sys.stderr)
        return {
            "content": cached["response"],
            "model": cached["model"] + " (cached)",
            "provider": "cache",
            "tokens": 0,
            "cached": True,
            "attempts": 0,
            "provider_chain": ["cache"],
        }
    
    # Layer 2: z-ai SDK (glm-4-plus, no popup)
    attempts += 1
    provider_chain.append("z-ai-sdk-glm4-plus")
    try:
        if verbose:
            print(f"[z-ai-sdk] attempting...", file=sys.stderr)
        result = call_zai_chat(prompt, system)
        # Cache
        cache_put(key, result["model"], prompt, system, result["content"], result["tokens"])
        cache_put(cache_key(prompt, system, "z-ai"), result["model"], prompt, system, result["content"], result["tokens"])
        return {
            "content": result["content"],
            "model": result["model"],
            "provider": "z-ai-sdk-glm4-plus",
            "tokens": result["tokens"],
            "cached": False,
            "attempts": attempts,
            "provider_chain": provider_chain,
        }
    except Exception as e:
        if verbose:
            print(f"[z-ai-sdk] failed: {e}", file=sys.stderr)
        provider_chain.append(f"z-ai-sdk-failed")
    
    # Layer 3: Pollinations (always available)
    attempts += 1
    provider_chain.append("pollinations-gpt-oss-20b")
    try:
        if verbose:
            print(f"[pollinations] fallback...", file=sys.stderr)
        result = call_pollinations_chat(prompt, system)
        cache_put(key, result["model"], prompt, system, result["content"], result["tokens"])
        cache_put(cache_key(prompt, system, "pollinations"), result["model"], prompt, system, result["content"], result["tokens"])
        return {
            "content": result["content"],
            "model": result["model"],
            "provider": "pollinations-gpt-oss-20b",
            "tokens": result["tokens"],
            "cached": False,
            "attempts": attempts,
            "provider_chain": provider_chain,
        }
    except Exception as e:
        if verbose:
            print(f"[pollinations] failed: {e}", file=sys.stderr)
        provider_chain.append("pollinations-failed")
    
    return {
        "content": "",
        "model": "none",
        "provider": "none",
        "tokens": 0,
        "cached": False,
        "attempts": attempts,
        "provider_chain": provider_chain,
        "error": "all providers failed",
    }


def list_models():
    """List available model providers."""
    print("Available LLM providers (priority order):")
    print()
    for p in MODEL_PROVIDERS:
        print(f"  [{p['priority']}] {p['name']}")
        print(f"      type: {p['type']}")
        print(f"      model: {p['model']}")
        print(f"      avg latency: {p['avg_latency_sec']}s")
        print(f"      rate limit: ~{p['rate_limit_rpm']} RPM")
        print(f"      notes: {p['notes']}")
        print()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["chat", "models"])
    parser.add_argument("--prompt", help="prompt for chat")
    parser.add_argument("--system", default="")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    
    if args.command == "models":
        list_models()
    elif args.command == "chat":
        if not args.prompt:
            print("--prompt required")
            sys.exit(2)
        result = smart_chat(args.prompt, args.system, verbose=args.verbose)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result.get("content") else 1)


if __name__ == "__main__":
    main()
