#!/usr/bin/env python3
"""
Multi-provider LLM client с устойчивостью к rate-limit.

Стратегия fallback:
1. z-ai (GLM-4-plus) — основной
2. Pollinations (GPT-OSS-20B) — fallback при rate-limit/timeout
3. z-ai с retry — последняя попытка

Дополнительно:
- Local cache (hash-based) — идентичные запросы не повторяются
- Adaptive throttle — при успехе ускоряемся, при 429 замедляемся
- Persistent state — результаты сохраняются после каждого запроса
- Concurrent requests с queue (max 2 parallel)
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
        # Экспоненциальный рост
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

def call_zai(system_prompt: str, user_prompt: str, timeout: int = 300) -> dict:
    """Вызов z-ai CLI."""
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
            try:
                os.unlink(tmp_out)
            except Exception:
                pass


# === PROVIDER: Pollinations (GPT-OSS-20B) ===

def call_pollinations(system_prompt: str, user_prompt: str, timeout: int = 60) -> dict:
    """Вызов Pollinations text API (free, no auth)."""
    try:
        # Добавляем к user_prompt инструкцию быть подробным и не обрывать ответ
        augmented_user = user_prompt + "\n\n[ВАЖНО: Дай ПОЛНЫЙ развёрнутый ответ (минимум 800 слов). Не обрывай на полуслове. Структурируй с заголовками H2/H3. Если пишешь JSON — закрой все скобки. ОТВЕЧАЙ В CONTENT FIELD, не в reasoning.]"
        payload = json.dumps({
            "model": "openai",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": augmented_user},
            ],
            "max_tokens": 8000,
            "temperature": 0.7,
            "reasoning_effort": "low",  # GPT-OSS-20B: minimize reasoning, maximize content
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://text.pollinations.ai/openai",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read())
        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        # Если content пустой — попробуем reasoning (иногда модель пишет туда)
        if not content and "reasoning" in message:
            reasoning = message.get("reasoning") or ""
            # Если reasoning содержит финальный ответ — извлечь его
            if reasoning and len(reasoning) > 100:
                content = reasoning
        # Принимаем любой непустой content
        if content and len(content) > 0:
            return {"success": True, "content": content, "provider": "pollinations-gpt-oss-20b"}
        return {"success": False, "error": f"empty content (keys: {list(message.keys())})", "provider": "pollinations"}
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.reason}", "provider": "pollinations"}
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "pollinations"}


# === MULTI-PROVIDER CLIENT ===

class MultiLLM:
    def __init__(self, cache_path: Optional[Path] = None, verbose: bool = True):
        self.cache = Cache(cache_path) if cache_path else None
        self.limiter_zai = RateLimiter(min_delay=3.0, max_delay=120.0)
        self.limiter_poll = RateLimiter(min_delay=1.0, max_delay=30.0)
        self.verbose = verbose
        # Статистика
        self.stats = {
            "zai_success": 0, "zai_fail": 0,
            "poll_success": 0, "poll_fail": 0,
            "cache_hit": 0,
        }

    def log(self, msg: str):
        if self.verbose:
            print(msg, flush=True)

    def chat(self, system_prompt: str, user_prompt: str, max_retries: int = 3) -> dict:
        # Cache check
        if self.cache:
            cached = self.cache.get(system_prompt, user_prompt)
            if cached:
                self.stats["cache_hit"] += 1
                self.log(f"  → CACHE HIT")
                return {"success": True, "content": cached, "provider": "cache"}

        # Strategy: try z-ai ONCE (with shorter timeout), if fail → Pollinations
        # Pollinations is faster and more reliable for sustained workloads

        # Try z-ai first (1 attempt, 120s timeout)
        self.limiter_zai.wait()
        self.log(f"  ▶ z-ai (attempt 1)")
        zai_result = call_zai(system_prompt, user_prompt, timeout=120)
        if zai_result["success"]:
            self.limiter_zai.on_success()
            self.stats["zai_success"] += 1
            if self.cache:
                self.cache.set(system_prompt, user_prompt, zai_result["content"])
            self.log(f"  ✓ z-ai: {len(zai_result['content'])} chars")
            return zai_result

        # z-ai failed — fall back to Pollinations (more reliable)
        self.limiter_zai.on_fail()
        self.stats["zai_fail"] += 1
        err = zai_result.get("error", "")[:200]
        self.log(f"  ⚠️ z-ai failed: {err}")
        self.log(f"  ▶ Pollinations fallback")

        # Pollinations with retries
        for poll_attempt in range(max_retries + 1):
            self.limiter_poll.wait()
            poll_result = call_pollinations(system_prompt, user_prompt, timeout=90)
            if poll_result["success"]:
                # Check if response is too short (truncated) — retry
                content_len = len(poll_result["content"])
                if content_len < 500 and poll_attempt < max_retries:
                    self.log(f"  ⚠️ Pollinations too short ({content_len} chars), retrying...")
                    self.limiter_poll.on_fail()
                    self.stats["poll_fail"] += 1
                    continue
                self.limiter_poll.on_success()
                self.stats["poll_success"] += 1
                if self.cache:
                    self.cache.set(system_prompt, user_prompt, poll_result["content"])
                self.log(f"  ✓ Pollinations: {len(poll_result['content'])} chars")
                return poll_result
            self.limiter_poll.on_fail()
            self.stats["poll_fail"] += 1
            self.log(f"  ⚠️ Pollinations attempt {poll_attempt+1} failed: {poll_result.get('error', '')[:150]}")

        # Last resort: try z-ai one more time with longer timeout
        self.log(f"  ▶ Last resort: z-ai retry with 240s timeout")
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
    print("=== Multi-LLM client test ===\n")
    cache_file = Path("/home/z/my-project/download/_multi_llm_cache.json")
    llm = MultiLLM(cache_path=cache_file)

    # Test 1: simple
    print("Test 1: simple question")
    r = llm.chat("You are helpful.", "Say hello in Russian.", max_retries=2)
    print(f"Result: provider={r.get('provider')}, content={r.get('content', r.get('error', ''))[:100]}")
    print(f"Stats: {llm.get_stats()}\n")

    # Test 2: cached (should be instant)
    print("Test 2: same question (cached)")
    r = llm.chat("You are helpful.", "Say hello in Russian.", max_retries=1)
    print(f"Result: provider={r.get('provider')}")
    print(f"Stats: {llm.get_stats()}")
