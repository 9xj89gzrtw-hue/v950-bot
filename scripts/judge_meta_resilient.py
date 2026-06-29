#!/usr/bin/env python3
"""
Устойчивый LLM-судья с:
- persistent state (judge_scores сохраняются после каждого теста)
- exponential backoff
- resume mode
- local cache

При падении продолжит с того места.
"""
import json
import subprocess
import os
import sys
import time
import hashlib
import random
from pathlib import Path

VERSION = sys.argv[1] if len(sys.argv) > 1 else "v9.79-FINAL"
SUFFIX = sys.argv[2] if len(sys.argv) > 2 else ""

OUT_DIR_BASE = f"/home/z/my-project/download/compiled_{VERSION.replace('.', '_')}"
OUT_DIR = Path(OUT_DIR_BASE + (f"_{SUFFIX}" if SUFFIX else ""))

JUDGE_PROMPT = """Ты — строгий судья промптов. Оцени скомпилированный промпт по 10-балльной шкале.

Критерии оценки (каждый 0-10):
1. **completeness** — покрывает ли промпт все требования задачи?
2. **clarity** — понятен ли промпт целевой LLM? Нет двусмысленностей?
3. **safety** — есть ли явные отказы для unsafe запросов? Edge cases?
4. **format_quality** — формат вывода чёткий? Есть примеры?
5. **actionability** — может ли целевая ЛЛМ сразу начать работать по этому промпту?

Выход — СТРИКТНО JSON:
{
  "completeness": <int 0-10>,
  "clarity": <int 0-10>,
  "safety": <int 0-10>,
  "format_quality": <int 0-10>,
  "actionability": <int 0-10>,
  "average": <float>,
  "weaknesses": ["конкретная слабость 1", "слабость 2", ...],
  "suggestions": ["конкретное улучшение 1", ...]
}
"""

SCORES_FILE = OUT_DIR / "_judge_scores.json"
CACHE_FILE = OUT_DIR / "_judge_cache.json"


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def cache_key(task: str, compiled: str) -> str:
    h = hashlib.sha256()
    h.update(task.encode())
    h.update(b"|||")
    h.update(compiled.encode())
    return h.hexdigest()[:32]


class RateLimiter:
    def __init__(self):
        self.min_delay = 3.0
        self.max_delay = 180.0
        self.current_delay = self.min_delay
        self.success = 0
        self.fail = 0

    def on_success(self):
        self.success += 1
        self.fail = 0
        if self.success >= 2:
            self.current_delay = max(self.min_delay, self.current_delay * 0.8)

    def on_fail(self):
        self.fail += 1
        self.success = 0
        factor = 2 ** min(self.fail, 5)
        self.current_delay = min(self.max_delay, self.min_delay * factor)

    def wait(self):
        jitter = random.uniform(0.7, 1.3)
        delay = self.current_delay * jitter
        time.sleep(delay)


def call_zai(system_prompt: str, user_prompt: str, max_retries: int = 8) -> dict:
    limiter = RateLimiter()
    last_error = None
    for attempt in range(max_retries):
        try:
            limiter.wait()
            tmp_out = "/tmp/_judge_resilient.json"
            cmd = ["z-ai", "chat", "-s", system_prompt, "-p", user_prompt, "-o", tmp_out]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0 and os.path.exists(tmp_out):
                data = json.loads(Path(tmp_out).read_text())
                content = None
                if "choices" in data:
                    content = data["choices"][0]["message"]["content"]
                elif "content" in data:
                    content = data["content"]
                if content and len(content) > 50:
                    limiter.on_success()
                    return {"success": True, "content": content, "attempts": attempt + 1}
                last_error = "empty content"
            else:
                stderr = result.stderr or ""
                last_error = stderr[:200]
                if "429" in stderr or "rate" in stderr.lower() or "Too Many" in stderr:
                    limiter.on_fail()
                    print(f"  ⚠️ rate-limit attempt {attempt+1}: wait {limiter.current_delay:.1f}s")
                elif "context deadline" in stderr or "timeout" in stderr.lower():
                    limiter.on_fail()
                    print(f"  ⚠️ timeout attempt {attempt+1}: wait {limiter.current_delay:.1f}s")
                else:
                    time.sleep(5)
        except subprocess.TimeoutExpired:
            last_error = "subprocess timeout"
            limiter.on_fail()
        except Exception as e:
            last_error = str(e)
            time.sleep(5)
    return {"success": False, "error": last_error, "attempts": max_retries}


def judge_all():
    results_file = OUT_DIR / "_all_results.json"
    if not results_file.exists():
        print(f"❌ {results_file} not found. Run test_meta_resilient.py first.")
        return

    data = json.loads(results_file.read_text())
    scores = load_json(SCORES_FILE, [])
    cache = load_json(CACHE_FILE, {})

    # Создаём map id → existing score
    existing = {s["id"]: s for s in scores if "id" in s}

    print("=" * 90)
    print(f"УСТОЙЧИВЫЙ LLM-JUDGE {VERSION} {SUFFIX}")
    print(f"Всего тестов: {len(data)}")
    print(f"Уже оценено: {len(existing)}")
    print(f"Кэш: {len(cache)} записей")
    print("=" * 90)

    new_scores = list(scores)  # копия
    sum_avg = 0
    count = 0

    for entry in data:
        test_id = entry["id"]

        # Resume: пропускаем если уже оценено
        if test_id in existing:
            s = existing[test_id]["scores"]
            if "average" in s:
                avg = s["average"]
                sum_avg += avg
                count += 1
                print(f"✓ {test_id:<35} avg={avg} (CACHED)")
                continue
            # если error — переоцениваем
            if "error" in s:
                print(f"↻ {test_id} — retry (previous error)")
            else:
                print(f"? {test_id} — incomplete, re-judging")

        print(f"\n▶ {test_id}")

        # Cache check
        key = cache_key(entry["task"], entry["compiled"])
        if key in cache:
            content = cache[key]
            print(f"  → CACHE HIT")
        else:
            user_msg = f"ЗАДАЧА:\n{entry['task']}\n\n===\n\nСКОМПИЛИРОВАННЫЙ ПРОМПТ:\n{entry['compiled']}"
            result = call_zai(JUDGE_PROMPT, user_msg)
            if not result["success"]:
                print(f"  ✗ FAILED: {result['error']}")
                # Сохраняем error и продолжаем
                new_entry = {"id": test_id, "scores": {"error": result["error"]}}
                # Заменяем или добавляем
                found = False
                for i, s in enumerate(new_scores):
                    if s.get("id") == test_id:
                        new_scores[i] = new_entry
                        found = True
                        break
                if not found:
                    new_scores.append(new_entry)
                save_json(SCORES_FILE, new_scores)
                continue

            content = result["content"]
            cache[key] = content
            save_json(CACHE_FILE, cache)
            print(f"  ✓ {len(content)} chars (attempts: {result['attempts']})")

        # Парсим JSON
        try:
            clean = content.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
            parsed = json.loads(clean)
            if "average" not in parsed and "completeness" in parsed:
                parsed["average"] = round(sum([
                    parsed["completeness"], parsed["clarity"], parsed["safety"],
                    parsed["format_quality"], parsed["actionability"]
                ]) / 5, 2)
            avg = parsed.get("average", 0)
            sum_avg += avg if isinstance(avg, (int, float)) else 0
            count += 1
            print(f"  → avg={avg}")

            # Update scores
            new_entry = {"id": test_id, "scores": parsed}
            found = False
            for i, s in enumerate(new_scores):
                if s.get("id") == test_id:
                    new_scores[i] = new_entry
                    found = True
                    break
            if not found:
                new_scores.append(new_entry)
            save_json(SCORES_FILE, new_scores)

        except Exception as e:
            print(f"  ✗ parse error: {e}")
            new_entry = {"id": test_id, "scores": {"error": str(e), "raw": content[:300]}}
            for i, s in enumerate(new_scores):
                if s.get("id") == test_id:
                    new_scores[i] = new_entry
                    break
            else:
                new_scores.append(new_entry)
            save_json(SCORES_FILE, new_scores)

    # Финальный отчёт
    print("\n" + "=" * 90)
    print(f"{'Тест':<35} {'Compl':>6} {'Clarity':>8} {'Safety':>7} {'Fmt':>4} {'Action':>7} {'AVG':>5}")
    print("=" * 90)
    sum_avg2 = 0
    count2 = 0
    for entry in new_scores:
        s = entry.get("scores", {})
        if "average" in s:
            avg = s["average"]
            sum_avg2 += avg
            count2 += 1
            print(f"{entry['id']:<35} {s.get('completeness','?'):>6} {s.get('clarity','?'):>8} {s.get('safety','?'):>7} {s.get('format_quality','?'):>4} {s.get('actionability','?'):>7} {avg:>5}")
            if "weaknesses" in s:
                for w in s["weaknesses"][:2]:
                    print(f"  ⚠️ {w}")
        else:
            print(f"{entry['id']:<35} ERROR: {s.get('error', 'unknown')[:50]}")
    print("=" * 90)
    if count2:
        print(f"{'AVERAGE':<35} {'':>6} {'':>8} {'':>7} {'':>4} {'':>7} {round(sum_avg2/count2, 2):>5}")


if __name__ == "__main__":
    judge_all()
