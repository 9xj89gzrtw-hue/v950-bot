#!/usr/bin/env python3
"""
MultiLLM v2: cascade of providers, smart fallback.

Priority:
1. z-ai (GLM-4-plus) — when available, best quality
2. Local Qwen2.5-3B (llama-cpp-python) — always available, no rate limits
3. Pollinations (GPT-OSS-20B) — free remote fallback

Features:
- Local cache (hash-based)
- Adaptive rate limiter (per-provider)
- Persistent state
- Long-output support (local model has no token limit)
- Reasoning_effort for Pollinations
"""
import json
import subprocess
import os
import sys
import time
import hashlib
import random
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional


# === RATE LIMITER ===

class RateLimiter:
    def __init__(self, min_delay=2.0, max_delay=120.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.current_delay = min_delay
        self.success_count = 0
        self.fail_count = 0

    def on_success(self):
        self.success_count += 1
        self.fail_count = 0
        if self.success_count >= 2:
            self.current_delay = max(self.min_delay, self.current_delay * 0.7)

    def on_fail(self):
        self.fail_count += 1
        self.success_count = 0
        factor = 2 ** min(self.fail_count, 5)
        self.current_delay = min(self.max_delay, self.min_delay * factor)

    def wait(self):
        jitter = random.uniform(0.7, 1.3)
        time.sleep(self.current_delay * jitter)


# === CACHE ===

class Cache:
    def __init__(self, path: Path):
        self.path = path
        self.data = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text())
            except Exception:
                self.data = {}

    def get(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        key = self._key(system_prompt, user_prompt)
        return self.data.get(key)

    def set(self, system_prompt: str, user_prompt: str, content: str):
        key = self._key(system_prompt, user_prompt)
        self.data[key] = content
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    def _key(self, system_prompt: str, user_prompt: str) -> str:
        h = hashlib.sha256()
        h.update(system_prompt.encode())
        h.update(b"|||")
        h.update(user_prompt.encode())
        return h.hexdigest()[:32]


# === PROVIDER: z-ai (GLM-4-plus) ===

def call_zai(system_prompt: str, user_prompt: str, timeout: int = 180) -> dict:
    tmp_out = f"/tmp/_zai_{os.getpid()}_{random.randint(0, 1000000)}.json"
    try:
        cmd = ["z-ai", "chat", "-s", system_prompt, "-p", user_prompt, "-o", tmp_out]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0 and os.path.exists(tmp_out):
            data = json.loads(Path(tmp_out).read_text())
            content = data.get("choices", [{}])[0].get("message", {}).get("content") or data.get("content")
            if content and len(content) > 30:
                return {"success": True, "content": content, "provider": "z-ai"}
        stderr = (result.stderr or "")[:300]
        return {"success": False, "error": stderr, "provider": "z-ai"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "subprocess timeout", "provider": "z-ai"}
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "z-ai"}
    finally:
        if os.path.exists(tmp_out):
            try: os.unlink(tmp_out)
            except Exception: pass


# === PROVIDER: Pollinations (GPT-OSS-20B) ===

def call_pollinations(system_prompt: str, user_prompt: str, timeout: int = 90) -> dict:
    try:
        augmented_user = user_prompt + "\n\n[ВАЖНО: Дай ПОЛНЫЙ развёрнутый ответ (минимум 800 слов). Не обрывай на полуслове. ОТВЕЧАЙ В CONTENT FIELD, не в reasoning.]"
        payload = json.dumps({
            "model": "openai",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": augmented_user},
            ],
            "max_tokens": 8000,
            "temperature": 0.7,
            "reasoning_effort": "low",
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://text.pollinations.ai/openai",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read())
        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        if not content and "reasoning" in message:
            reasoning = message.get("reasoning") or ""
            if reasoning and len(reasoning) > 100:
                content = reasoning
        if content and len(content) > 0:
            return {"success": True, "content": content, "provider": "pollinations-gpt-oss-20b"}
        return {"success": False, "error": f"empty content", "provider": "pollinations"}
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "pollinations"}


# === PROVIDER: Local Llama (Qwen2.5-3B via llama-cpp-python) ===

_LOCAL_LLM = None
_LOCAL_MODEL_PATH = "/home/z/my-project/models/qwen2.5-3b-instruct-q5_k_m.gguf"

def get_local_llm():
    global _LOCAL_LLM
    if _LOCAL_LLM is None:
        try:
            from llama_cpp import Llama
            if not Path(_LOCAL_MODEL_PATH).exists():
                return None
            _LOCAL_LLM = Llama(
                model_path=_LOCAL_MODEL_PATH,
                n_ctx=4096,
                n_threads=4,
                n_gpu_layers=0,
                verbose=False,
            )
        except Exception as e:
            print(f"  ⚠️ Local LLM init failed: {e}")
            return None
    return _LOCAL_LLM


def call_local(system_prompt: str, user_prompt: str, max_tokens: int = 2048) -> dict:
    llm = get_local_llm()
    if llm is None:
        return {"success": False, "error": "local model not available", "provider": "local"}
    try:
        out = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt[:3000]},  # truncate to fit
                {"role": "user", "content": user_prompt[:4000]},
            ],
            max_tokens=max_tokens,
            temperature=0.7,
            top_p=0.9,
        )
        content = out["choices"][0]["message"]["content"]
        if content and len(content) > 0:
            return {"success": True, "content": content, "provider": "local-qwen2.5-3b"}
        return {"success": False, "error": "empty content", "provider": "local"}
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "local"}


# === MULTI-PROVIDER CLIENT v2 ===

class MultiLLMv2:
    """
    Smart cascade:
    1. z-ai (best quality, may be rate-limited)
    2. Pollinations (decent remote fallback)
    3. Local Qwen2.5-3B (always available, no rate limits, but smaller/slower)
    """
    def __init__(self, cache_path: Optional[Path] = None, verbose: bool = True):
        self.cache = Cache(cache_path) if cache_path else None
        self.limiter_zai = RateLimiter(min_delay=3.0, max_delay=120.0)
        self.limiter_poll = RateLimiter(min_delay=1.0, max_delay=30.0)
        self.limiter_local = RateLimiter(min_delay=0.5, max_delay=5.0)  # local is fast
        self.verbose = verbose
        self.stats = {
            "zai_success": 0, "zai_fail": 0,
            "poll_success": 0, "poll_fail": 0,
            "local_success": 0, "local_fail": 0,
            "cache_hit": 0,
        }
        # Try to preload local model
        if self.verbose:
            print("  [init] Preloading local Qwen2.5-3B...", flush=True)
        get_local_llm()

    def log(self, msg: str):
        if self.verbose:
            print(msg, flush=True)

    def chat(self, system_prompt: str, user_prompt: str, max_retries: int = 2, min_length: int = 200) -> dict:
        # Cache check
        if self.cache:
            cached = self.cache.get(system_prompt, user_prompt)
            if cached and len(cached) >= min_length:
                self.stats["cache_hit"] += 1
                self.log(f"  → CACHE HIT ({len(cached)} chars)")
                return {"success": True, "content": cached, "provider": "cache"}

        # === STAGE 1: Try z-ai once ===
        self.limiter_zai.wait()
        self.log(f"  ▶ z-ai (attempt 1)")
        zai_result = call_zai(system_prompt, user_prompt, timeout=120)
        if zai_result["success"] and len(zai_result["content"]) >= min_length:
            self.limiter_zai.on_success()
            self.stats["zai_success"] += 1
            if self.cache:
                self.cache.set(system_prompt, user_prompt, zai_result["content"])
            self.log(f"  ✓ z-ai: {len(zai_result['content'])} chars")
            return zai_result

        # z-ai failed or too short
        self.limiter_zai.on_fail()
        self.stats["zai_fail"] += 1
        err = zai_result.get("error", "")[:150]
        self.log(f"  ⚠️ z-ai failed: {err}")

        # === STAGE 2: Try Pollinations (decent remote) ===
        for poll_attempt in range(max_retries + 1):
            self.limiter_poll.wait()
            self.log(f"  ▶ Pollinations attempt {poll_attempt + 1}")
            poll_result = call_pollinations(system_prompt, user_prompt, timeout=90)
            if poll_result["success"]:
                content_len = len(poll_result["content"])
                if content_len >= min_length:
                    self.limiter_poll.on_success()
                    self.stats["poll_success"] += 1
                    if self.cache:
                        self.cache.set(system_prompt, user_prompt, poll_result["content"])
                    self.log(f"  ✓ Pollinations: {content_len} chars")
                    return poll_result
                else:
                    self.log(f"  ⚠️ Pollinations too short ({content_len} chars)")
            else:
                self.log(f"  ⚠️ Pollinations failed: {poll_result.get('error', '')[:100]}")
            self.limiter_poll.on_fail()
            self.stats["poll_fail"] += 1

        # === STAGE 3: Local Qwen2.5-3B (always available) ===
        self.log(f"  ▶ Local Qwen2.5-3B (always available)")
        self.limiter_local.wait()
        # Use larger max_tokens for local (no rate limit)
        local_result = call_local(system_prompt, user_prompt, max_tokens=3000)
        if local_result["success"] and len(local_result["content"]) > 0:
            self.limiter_local.on_success()
            self.stats["local_success"] += 1
            if self.cache:
                self.cache.set(system_prompt, user_prompt, local_result["content"])
            self.log(f"  ✓ Local Qwen2.5-3B: {len(local_result['content'])} chars")
            return local_result

        self.limiter_local.on_fail()
        self.stats["local_fail"] += 1
        self.log(f"  ⚠️ Local failed: {local_result.get('error', '')[:100]}")

        # === STAGE 4: Last resort — z-ai with long timeout ===
        self.log(f"  ▶ Last resort: z-ai with 240s timeout")
        self.limiter_zai.wait()
        zai_result = call_zai(system_prompt, user_prompt, timeout=240)
        if zai_result["success"]:
            self.stats["zai_success"] += 1
            if self.cache:
                self.cache.set(system_prompt, user_prompt, zai_result["content"])
            self.log(f"  ✓ z-ai (last resort): {len(zai_result['content'])} chars")
            return zai_result

        self.stats["zai_fail"] += 1
        return {"success": False, "error": "All providers failed", "provider": "none", "stats": self.stats}

    def get_stats(self) -> dict:
        return self.stats.copy()


# === TEST ===

if __name__ == "__main__":
    print("=== MultiLLM v2 test ===\n")
    cache_file = Path("/home/z/my-project/download/_multi_llm_v2_cache.json")
    llm = MultiLLMv2(cache_path=cache_file)

    print("\nTest 1: simple")
    r = llm.chat("You are helpful.", "Say hello in Russian. Write 2 sentences about AI.", max_retries=1, min_length=50)
    print(f"Result: provider={r.get('provider')}")
    print(f"Content: {r.get('content', r.get('error', ''))[:300]}")
    print(f"Stats: {llm.get_stats()}")
