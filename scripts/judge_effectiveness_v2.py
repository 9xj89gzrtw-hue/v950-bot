#!/usr/bin/env python3
"""
LLM-judge с multi-provider fallback.
Использует MultiLLM: z-ai → Pollinations fallback.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, '/home/z/my-project/scripts')
from multi_llm import MultiLLM

VERSION = sys.argv[1] if len(sys.argv) > 1 else "v9.86-WORLDCLASS4"
# Normalize version for path: strip "-FINAL" suffix
VERSION_FOR_PATH = VERSION.replace("-FINAL", "")
OUT_DIR = Path(f"/home/z/my-project/download/effectiveness_{VERSION_FOR_PATH.replace('.', '_')}")
SCORES_FILE = OUT_DIR / "_judge_scores.json"
CACHE_FILE = OUT_DIR / "_judge_cache.json"

JUDGE_PROMPT = """Ты — судья эффективности. Оцени OUTPUT по 10-балльной шкале.

КРИТИЧНО: ОТВЕТ — КОРОТКИЙ JSON (максимум 500 символов). Только 5 чисел + average + verdict. Никаких длинных объяснений в what_would_fail (максимум 1 короткая фраза).

Формат (СТРОГО):
{"effectiveness": <0-10>, "first_try_quality": <0-10>, "actionability": <0-10>, "realistic_outcome": <0-10>, "completeness": <0-10>, "average": <float>, "verdict": "BEST_IN_WORLD|EXCELLENT|GOOD|NEEDS_WORK|POOR", "would_user_succeed": "yes|no|partially", "main_weakness": "<ОДНА короткая фраза>"}

Шкала: 10=лучший в мире, 9=отлично, 8=очень хорошо, 7=хорошо, 6=средне, ≤5=плохо.

Критерии:
- effectiveness: доставит ли обещанный результат?
- first_try_quality: можно ли использовать с первой попытки?
- actionability: конкретные шаги сегодня?
- realistic_outcome: реалистично?
- completeness: все требования покрыты?

ТОЛЬКО JSON. Начни с { закончи }. Без markdown.
"""


def load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def judge_all():
    results_file = OUT_DIR / "_all_results.json"
    if not results_file.exists():
        print(f"❌ {results_file} not found")
        return
    data = json.loads(results_file.read_text())
    scores = load_json(SCORES_FILE, [])
    existing = {s["id"]: s for s in scores if "id" in s}

    llm = MultiLLM(cache_path=CACHE_FILE, verbose=True)

    print("=" * 100)
    print(f"ЭФФЕКТИВНОСТЬ LLM-JUDGE {VERSION} (multi-provider)")
    print("=" * 100)

    new_scores = list(scores)

    for entry in data:
        test_id = entry["id"]
        if "output" not in entry:
            print(f"\n✗ {test_id} — NO OUTPUT")
            continue

        if test_id in existing and "average" in existing[test_id].get("scores", {}):
            s = existing[test_id]["scores"]
            print(f"\n✓ {test_id} — CACHED avg={s['average']} verdict={s.get('verdict', '?')}")
            continue

        print(f"\n▶ {test_id}")

        user_msg = f"""USER TASK:
{entry.get('user_task', '')}

===
OUTPUT (то что сгенерировала LLM по домен-промпту):
{entry['output']}

===
META TASK (для контекста — что должен был делать домен-промпт):
{entry.get('meta_task', '')}

Помни: выход — чистый JSON без markdown, без code fence.
"""
        result = llm.chat(JUDGE_PROMPT, user_msg, max_retries=3)
        if not result["success"]:
            print(f"  ✗ FAILED: {result.get('error')}")
            new_entry = {"id": test_id, "scores": {"error": result.get("error", "failed")}}
            for i, s in enumerate(new_scores):
                if s.get("id") == test_id:
                    new_scores[i] = new_entry
                    break
            else:
                new_scores.append(new_entry)
            save_json(SCORES_FILE, new_scores)
            continue

        content = result["content"]
        print(f"  ✓ {len(content)} chars (provider: {result['provider']})")

        try:
            clean = content.strip()
            # Remove code fence if present
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
            # Try to extract JSON from text (find first { and last })
            if "{" in clean and "}" in clean:
                start = clean.find("{")
                end = clean.rfind("}") + 1
                clean = clean[start:end]
            parsed = json.loads(clean)
            if "average" not in parsed and "effectiveness" in parsed:
                parsed["average"] = round(sum([
                    parsed["effectiveness"], parsed["first_try_quality"], parsed["actionability"],
                    parsed["realistic_outcome"], parsed["completeness"]
                ]) / 5, 2)
            print(f"  → avg={parsed.get('average', '?')} verdict={parsed.get('verdict', '?')}")
            new_entry = {"id": test_id, "scores": parsed}
            for i, s in enumerate(new_scores):
                if s.get("id") == test_id:
                    new_scores[i] = new_entry
                    break
            else:
                new_scores.append(new_entry)
            save_json(SCORES_FILE, new_scores)
        except Exception as e:
            print(f"  ✗ parse error: {e}")
            new_entry = {"id": test_id, "scores": {"error": str(e), "raw": content[:3000]}}
            for i, s in enumerate(new_scores):
                if s.get("id") == test_id:
                    new_scores[i] = new_entry
                    break
            else:
                new_scores.append(new_entry)
            save_json(SCORES_FILE, new_scores)

    # Финальный отчёт
    print("\n" + "=" * 100)
    print(f"{'Тест':<25} {'Eff':>4} {'1st':>4} {'Act':>4} {'Real':>5} {'Compl':>6} {'AVG':>5} {'Verdict':<18} {'Succeed':<10}")
    print("=" * 100)
    sum_avg = 0
    count = 0
    for entry in new_scores:
        s = entry.get("scores", {})
        if "average" in s:
            avg = s["average"]
            sum_avg += avg
            count += 1
            print(f"{entry['id']:<25} {s.get('effectiveness','?'):>4} {s.get('first_try_quality','?'):>4} {s.get('actionability','?'):>4} {s.get('realistic_outcome','?'):>5} {s.get('completeness','?'):>6} {avg:>5} {s.get('verdict','?'):<18} {s.get('would_user_succeed','?'):<10}")
            if "what_would_fail" in s:
                for w in s["what_would_fail"][:2]:
                    print(f"  ❌ {w}")
        else:
            print(f"{entry['id']:<25} ERROR: {str(s.get('error', 'unknown'))[:50]}")
    print("=" * 100)
    if count:
        print(f"{'AVERAGE':<25} {'':>4} {'':>4} {'':>4} {'':>5} {'':>6} {round(sum_avg/count, 2):>5}")

    print(f"\nLLM stats: {llm.get_stats()}")


if __name__ == "__main__":
    judge_all()
