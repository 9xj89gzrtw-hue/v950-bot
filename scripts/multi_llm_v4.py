#!/usr/bin/env python3
"""
MultiLLM v4: cascade с встроенным Truth Gateway.

CASCADE:
1. z-ai (GLM-5) — primary
2. Local Qwen3-4B — smart, fast, no rate limit
3. Pollinations (GPT-OSS-20B) — remote fallback

TRUTH GATEWAY (structural anti-lie):
- После генерации OUTPUT автоматически извлекает factual claims
- Проверяет каждый через web_search (multi-source)
- Помечает [VERIFIED: URL] или [UNVERIFIED: needs manual check]
- Возвращает annotated OUTPUT

Если web_search недоступен — все changing facts помечаются [UNVERIFIED].
Это структурно не даёт модели выдавать ложь за факт.
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

# Import truth_gateway
sys.path.insert(0, '/home/z/my-project/scripts')
from truth_gateway import truth_gateway, extract_claims


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
        self.current_delay = min(self.max_delay, self.min_delay * (2 ** min(self.fail_count, 5)))

    def wait(self):
        time.sleep(self.current_delay * random.uniform(0.7, 1.3))


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
        return self.data.get(self._key(system_prompt, user_prompt))

    def set(self, system_prompt: str, user_prompt: str, content: str):
        self.data[self._key(system_prompt, user_prompt)] = content
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    def _key(self, system_prompt: str, user_prompt: str) -> str:
        h = hashlib.sha256()
        h.update(system_prompt.encode())
        h.update(b"|||")
        h.update(user_prompt.encode())
        return h.hexdigest()[:32]


def call_zai(system_prompt: str, user_prompt: str, timeout: int = 120) -> dict:
    tmp_out = f"/tmp/_zai_{os.getpid()}_{random.randint(0, 1000000)}.json"
    try:
        cmd = ["z-ai", "chat", "-s", system_prompt, "-p", user_prompt, "-o", tmp_out]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0 and os.path.exists(tmp_out):
            data = json.loads(Path(tmp_out).read_text())
            content = data.get("choices", [{}])[0].get("message", {}).get("content") or data.get("content")
            if content and len(content) > 30:
                return {"success": True, "content": content, "provider": "z-ai-glm5"}
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


def call_pollinations(system_prompt: str, user_prompt: str, timeout: int = 90) -> dict:
    try:
        augmented_user = user_prompt + "\n\n[ВАЖНО: Дай ПОЛНЫЙ развёрнутый ответ. ОТВЕЧАЙ В CONTENT FIELD, не в reasoning.]"
        payload = json.dumps({
            "model": "openai",
            "messages": [
                {"role": "system", "content": system_prompt[:5000]},
                {"role": "user", "content": augmented_user[:5000]},
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
        return {"success": False, "error": "empty content", "provider": "pollinations"}
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "pollinations"}


# === LOCAL Qwen3-4B (newest, smart, fast) ===

_LOCAL_LLM = None
_LOCAL_MODELS = [
    "/home/z/my-project/models/Qwen3-4B-Q5_K_M.gguf",  # primary (newest 2025)
    "/home/z/my-project/models/Qwen2.5-7B-Instruct-Q5_K_M.gguf",  # fallback (smarter)
    "/home/z/my-project/models/qwen2.5-3b-instruct-q5_k_m.gguf",  # last resort (fast)
]


def get_local_llm():
    global _LOCAL_LLM
    if _LOCAL_LLM is None:
        try:
            from llama_cpp import Llama
            for path in _LOCAL_MODELS:
                if Path(path).exists():
                    print(f"  [init] Loading local model: {Path(path).name}", flush=True)
                    _LOCAL_LLM = Llama(
                        model_path=path,
                        n_ctx=4096,
                        n_threads=4,
                        n_gpu_layers=0,
                        verbose=False,
                        flash_attn=True,
                    )
                    print(f"  [init] ✓ Loaded {Path(path).name}", flush=True)
                    break
            if _LOCAL_LLM is None:
                return None
        except Exception as e:
            print(f"  [init] Local LLM init failed: {e}", flush=True)
            return None
    return _LOCAL_LLM


def call_local(system_prompt: str, user_prompt: str, max_tokens: int = 2500) -> dict:
    llm = get_local_llm()
    if llm is None:
        return {"success": False, "error": "local model not available", "provider": "local"}
    try:
        # For Qwen3-4B which uses thinking mode, add /no_think to user prompt
        augmented = user_prompt
        if 'qwen3' in str(getattr(llm, 'model_path', '')).lower():
            augmented = user_prompt + " /no_think"
        
        out = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt[:3000]},
                {"role": "user", "content": augmented[:4000]},
            ],
            max_tokens=max_tokens,
            temperature=0.5,
            top_p=0.9,
        )
        content = out["choices"][0]["message"]["content"]
        # Strip <think>...</think> tags if present (Qwen3 reasoning)
        if '<think>' in content:
            import re
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        if content and len(content) > 0:
            return {"success": True, "content": content, "provider": "local-qwen3-4b"}
        return {"success": False, "error": "empty content", "provider": "local"}
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "local"}


# === MULTI-PROVIDER CLIENT v4 (with Truth Gateway) ===

class MultiLLMv4:
    """
    Cascade + Truth Gateway:
    1. z-ai (best quality)
    2. Local Qwen3-4B (always available, fast, smart)
    3. Pollinations (remote fallback)
    
    After generation: truth_gateway verifies all factual claims.
    """
    def __init__(self, cache_path: Optional[Path] = None, verbose: bool = True,
                 enable_truth_gateway: bool = True, max_verify_claims: int = 8):
        self.cache = Cache(cache_path) if cache_path else None
        self.limiter_zai = RateLimiter(min_delay=3.0, max_delay=120.0)
        self.limiter_poll = RateLimiter(min_delay=1.0, max_delay=30.0)
        self.limiter_local = RateLimiter(min_delay=0.3, max_delay=3.0)
        self.verbose = verbose
        self.enable_tg = enable_truth_gateway
        self.max_verify = max_verify_claims
        self.stats = {
            "zai_success": 0, "zai_fail": 0,
            "poll_success": 0, "poll_fail": 0,
            "local_success": 0, "local_fail": 0,
            "cache_hit": 0,
            "tg_verified": 0, "tg_unverified": 0, "tg_skipped": 0,
        }
        if self.verbose:
            print("  [init] Preloading local model...", flush=True)
        get_local_llm()

    def log(self, msg: str):
        if self.verbose:
            print(msg, flush=True)

    def chat(self, system_prompt: str, user_prompt: str, max_retries: int = 2,
             min_length: int = 200, verify: bool = True) -> dict:
        # Cache check
        if self.cache:
            cached = self.cache.get(system_prompt, user_prompt)
            if cached and len(cached) >= min_length:
                self.stats["cache_hit"] += 1
                self.log(f"  → CACHE HIT ({len(cached)} chars)")
                return {"success": True, "content": cached, "provider": "cache",
                        "truth_gateway": {"skipped": "cache hit"}}

        # Cascade: zai → local → poll
        for provider in ["zai", "local", "poll"]:
            self.log(f"  ▶ {provider}")
            if provider == "zai":
                self.limiter_zai.wait()
                result = call_zai(system_prompt, user_prompt, timeout=120)
            elif provider == "local":
                self.limiter_local.wait()
                result = call_local(system_prompt, user_prompt, max_tokens=2500)
            else:
                self.limiter_poll.wait()
                result = call_pollinations(system_prompt, user_prompt, timeout=90)

            if result["success"] and len(result["content"]) >= min_length:
                if provider == "zai":
                    self.limiter_zai.on_success()
                    self.stats["zai_success"] += 1
                elif provider == "local":
                    self.limiter_local.on_success()
                    self.stats["local_success"] += 1
                else:
                    self.limiter_poll.on_success()
                    self.stats["poll_success"] += 1
                
                content = result["content"]
                
                # === TRUTH GATEWAY (structural anti-lie) ===
                tg_report = None
                if self.enable_tg and verify:
                    self.log(f"  [truth_gateway] Verifying claims...")
                    tg_report = truth_gateway(content, verify=True, max_claims=self.max_verify)
                    content = tg_report["annotated"]
                    self.stats["tg_verified"] += tg_report["stats"]["verified"]
                    self.stats["tg_unverified"] += tg_report["stats"]["unverified"]
                    self.stats["tg_skipped"] += tg_report["stats"]["skipped"]
                    self.log(f"  [truth_gateway] {tg_report['summary']}")
                
                if self.cache:
                    self.cache.set(system_prompt, user_prompt, content)
                self.log(f"  ✓ {provider}: {len(content)} chars (with TG annotations)")
                return {
                    "success": True,
                    "content": content,
                    "provider": result["provider"],
                    "truth_gateway": tg_report["stats"] if tg_report else None,
                    "tg_summary": tg_report["summary"] if tg_report else None,
                }

            err = result.get("error", "too short")[:150]
            self.log(f"  ⚠️ {provider} failed: {err}")
            if provider == "zai":
                self.limiter_zai.on_fail()
                self.stats["zai_fail"] += 1
            elif provider == "local":
                self.limiter_local.on_fail()
                self.stats["local_fail"] += 1
            else:
                self.limiter_poll.on_fail()
                self.stats["poll_fail"] += 1

        return {"success": False, "error": "All providers failed", "provider": "none", "stats": self.stats}

    def get_stats(self) -> dict:
        return self.stats.copy()


if __name__ == "__main__":
    print("=== MultiLLM v4 test (with Truth Gateway) ===\n")
    cache_file = Path("/home/z/my-project/download/_multi_llm_v4_cache.json")
    llm = MultiLLMv4(cache_path=cache_file)

    print("\nTest: fact-containing output")
    r = llm.chat(
        "You are a helpful assistant.",
        "Briefly describe: latest GLM model, latest GPT model, NVDA stock price, Next.js version.",
        max_retries=1,
        min_length=50,
        verify=True
    )
    print(f"\n{'='*70}")
    print(f"Provider: {r.get('provider')}")
    print(f"TG stats: {r.get('truth_gateway')}")
    print(f"TG summary: {r.get('tg_summary')}")
    print(f"\n{'='*70}")
    print("CONTENT:")
    print(r.get('content', r.get('error', '')))
    print(f"\n{'='*70}")
    print(f"Stats: {llm.get_stats()}")
