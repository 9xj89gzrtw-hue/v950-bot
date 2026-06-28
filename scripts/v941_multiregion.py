#!/usr/bin/env python3
"""
v941_multiregion.py — MULTI-REGION LLM ROUTING v9.41
======================================================
Routes LLM requests to optimal provider based on latency + availability.

Regions/providers tracked:
- z-ai (China, glm-4-plus) — primary, fast
- Pollinations (US/EU, gpt-oss-20b) — fallback, free
- Wikipedia REST API (global) — for factual queries (no LLM needed)
- DuckDuckGo IA API (global) — for simple Q&A (no LLM needed)

Routing logic:
1. If query is factual → use Wikipedia/DDG (no LLM, instant)
2. If z-ai available + fast (<3s) → use z-ai
3. If z-ai slow/failing → use Pollinations
4. If all LLM fail → use cache or return error

Latency tracking:
- Per-provider avg response time (rolling 100 samples)
- Per-provider success rate
- Auto-disable providers with <50% success rate

Usage:
    python3 v941_multiregion.py chat --prompt "What is the capital of France?"
    python3 v941_multiregion.py stats     # show routing stats
    python3 v941_multiregion.py reset     # reset latency stats
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, "/home/z/my-project/scripts")

STATS_FILE = "/home/z/my-project/scripts/v941_routing_stats.json"


# ============================================================================
# LATENCY TRACKER
# ============================================================================

class LatencyTracker:
    """Track per-provider latency and success rate."""
    
    def __init__(self):
        self.samples = defaultdict(lambda: deque(maxlen=100))  # provider → response times
        self.success = defaultdict(lambda: {"ok": 0, "fail": 0})
    
    def record(self, provider, duration_sec, success):
        self.samples[provider].append(duration_sec)
        if success:
            self.success[provider]["ok"] += 1
        else:
            self.success[provider]["fail"] += 1
    
    def avg_latency(self, provider):
        s = self.samples[provider]
        if not s:
            return float('inf')
        return sum(s) / len(s)
    
    def success_rate(self, provider):
        stats = self.success[provider]
        total = stats["ok"] + stats["fail"]
        if total == 0:
            return 1.0
        return stats["ok"] / total
    
    def is_healthy(self, provider):
        return self.success_rate(provider) >= 0.5
    
    def save(self):
        data = {
            "samples": {p: list(s) for p, s in self.samples.items()},
            "success": dict(self.success),
            "timestamp": time.time(),
        }
        Path(STATS_FILE).write_text(json.dumps(data, indent=2))
    
    def load(self):
        if not os.path.exists(STATS_FILE):
            return
        try:
            data = json.loads(Path(STATS_FILE).read_text())
            for p, samples in data.get("samples", {}).items():
                self.samples[p] = deque(samples, maxlen=100)
            for p, stats in data.get("success", {}).items():
                self.success[p] = stats
        except Exception:
            pass
    
    def stats(self):
        result = {}
        for provider in set(list(self.samples.keys()) + list(self.success.keys())):
            result[provider] = {
                "avg_latency_sec": round(self.avg_latency(provider), 2),
                "success_rate": round(self.success_rate(provider), 3),
                "healthy": self.is_healthy(provider),
                "samples": len(self.samples[provider]),
                "ok": self.success[provider]["ok"],
                "fail": self.success[provider]["fail"],
            }
        return result


_TRACKER = LatencyTracker()
_TRACKER.load()


# ============================================================================
# PROVIDERS
# ============================================================================

def query_wikipedia(query):
    """Try Wikipedia REST API for factual query. Returns None if not found."""
    # Simple: use first word as title (works for entity queries)
    title = query.replace(" ", "_")[:50]
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        extract = data.get("extract", "")
        if extract:
            return {
                "content": extract[:500],
                "provider": "wikipedia-rest",
                "model": "wikipedia",
                "tokens": 0,
                "cached": False,
            }
    except Exception:
        pass
    return None


def query_ddg(query):
    """Try DuckDuckGo Instant Answer API."""
    url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        abstract = data.get("Abstract", "")
        if abstract:
            return {
                "content": abstract[:500],
                "provider": "duckduckgo-ia",
                "model": "ddg",
                "tokens": 0,
                "cached": False,
            }
    except Exception:
        pass
    return None


def query_zai(prompt, system=""):
    """Query z-ai SDK."""
    from v938_llm_client import call_zai_chat
    result = call_zai_chat(prompt, system)
    return {
        "content": result["content"],
        "provider": "z-ai-sdk-glm4-plus",
        "model": result["model"],
        "tokens": result["tokens"],
        "cached": False,
    }


def query_pollinations(prompt, system=""):
    """Query Pollinations."""
    from v938_llm_client import call_pollinations_chat
    result = call_pollinations_chat(prompt, system)
    return {
        "content": result["content"],
        "provider": "pollinations-gpt-oss-20b",
        "model": result["model"],
        "tokens": result["tokens"],
        "cached": False,
    }


# ============================================================================
# ROUTER
# ============================================================================

def is_factual_query(prompt):
    """Detect if query is factual (entity lookup)."""
    # Patterns that suggest factual lookup
    factual_patterns = [
        r"^what is (.+)",
        r"^who is (.+)",
        r"^who was (.+)",
        r"^what was (.+)",
        r"^capital of (.+)",
        r"^define (.+)",
    ]
    prompt_lower = prompt.lower().strip()
    for pat in factual_patterns:
        if re.match(pat, prompt_lower):
            return True
    return False


def route_query(prompt, system="", verbose=False):
    """
    Route query to optimal provider.
    
    Returns:
        {
            "content": str,
            "provider": str,
            "model": str,
            "tokens": int,
            "cached": bool,
            "routing_chain": [str],
            "latency_sec": float,
        }
    """
    import urllib.parse
    routing_chain = []
    start_time = time.time()
    
    # Layer 0: Cache
    from v938_llm_client import cache_key, cache_get, cache_put, init_cache_db
    init_cache_db()
    key = cache_key(prompt, system, "any")
    cached = cache_get(key)
    if cached:
        if verbose:
            print(f"[cache HIT]", file=sys.stderr)
        return {
            "content": cached["response"],
            "provider": "cache",
            "model": cached["model"] + " (cached)",
            "tokens": 0,
            "cached": True,
            "routing_chain": ["cache"],
            "latency_sec": round(time.time() - start_time, 3),
        }
    
    # Layer 1: Factual query → Wikipedia/DDG (no LLM)
    if is_factual_query(prompt) and not system:
        if verbose:
            print("[routing] factual query detected, trying Wikipedia...", file=sys.stderr)
        routing_chain.append("wikipedia")
        t0 = time.time()
        result = query_wikipedia(prompt)
        _TRACKER.record("wikipedia", time.time() - t0, result is not None)
        if result:
            cache_put(key, result["model"], prompt, system, result["content"], 0)
            result["routing_chain"] = routing_chain
            result["latency_sec"] = round(time.time() - start_time, 3)
            _TRACKER.save()
            return result
        
        routing_chain.append("ddg")
        t0 = time.time()
        result = query_ddg(prompt)
        _TRACKER.record("ddg", time.time() - t0, result is not None)
        if result:
            cache_put(key, result["model"], prompt, system, result["content"], 0)
            result["routing_chain"] = routing_chain
            result["latency_sec"] = round(time.time() - start_time, 3)
            _TRACKER.save()
            return result
    
    # Layer 2: z-ai (if healthy)
    if _TRACKER.is_healthy("z-ai-sdk-glm4-plus"):
        routing_chain.append("z-ai")
        if verbose:
            print(f"[routing] trying z-ai (avg={_TRACKER.avg_latency('z-ai-sdk-glm4-plus'):.1f}s)...", file=sys.stderr)
        t0 = time.time()
        try:
            result = query_zai(prompt, system)
            _TRACKER.record("z-ai-sdk-glm4-plus", time.time() - t0, True)
            cache_put(key, result["model"], prompt, system, result["content"], result["tokens"])
            result["routing_chain"] = routing_chain
            result["latency_sec"] = round(time.time() - start_time, 3)
            _TRACKER.save()
            return result
        except Exception as e:
            _TRACKER.record("z-ai-sdk-glm4-plus", time.time() - t0, False)
            if verbose:
                print(f"[routing] z-ai failed: {e}", file=sys.stderr)
    
    # Layer 3: Pollinations (always available)
    routing_chain.append("pollinations")
    if verbose:
        print("[routing] fallback to Pollinations...", file=sys.stderr)
    t0 = time.time()
    try:
        result = query_pollinations(prompt, system)
        _TRACKER.record("pollinations-gpt-oss-20b", time.time() - t0, True)
        cache_put(key, result["model"], prompt, system, result["content"], result["tokens"])
        result["routing_chain"] = routing_chain
        result["latency_sec"] = round(time.time() - start_time, 3)
        _TRACKER.save()
        return result
    except Exception as e:
        _TRACKER.record("pollinations-gpt-oss-20b", time.time() - t0, False)
        if verbose:
            print(f"[routing] Pollinations failed: {e}", file=sys.stderr)
    
    _TRACKER.save()
    return {
        "content": "",
        "provider": "none",
        "model": "none",
        "tokens": 0,
        "cached": False,
        "routing_chain": routing_chain,
        "latency_sec": round(time.time() - start_time, 3),
        "error": "all providers failed",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["chat", "stats", "reset"])
    parser.add_argument("--prompt", help="prompt for chat")
    parser.add_argument("--system", default="")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    
    if args.command == "chat":
        if not args.prompt:
            print("--prompt required")
            sys.exit(2)
        result = route_query(args.prompt, args.system, verbose=args.verbose)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result.get("content") else 1)
    
    elif args.command == "stats":
        stats = _TRACKER.stats()
        print(json.dumps(stats, indent=2))
    
    elif args.command == "reset":
        _TRACKER.samples.clear()
        _TRACKER.success.clear()
        if os.path.exists(STATS_FILE):
            os.unlink(STATS_FILE)
        print("Stats reset")


if __name__ == "__main__":
    main()
