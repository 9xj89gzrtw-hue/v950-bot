#!/usr/bin/env python3
"""
Local LLM judge v2: использует Qwen2.5-7B для стабильной оценки.
Локальная модель не имеет rate limit, не обрезает ответы, стабильна.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, '/home/z/my-project/scripts')
from multi_llm_v3 import call_local, get_local_llm

VERSION = sys.argv[1] if len(sys.argv) > 1 else "v9.88-WEBCHECK"
OUT_DIR = Path(f"/home/z/my-project/download/effectiveness_{VERSION.replace('.', '_')}")
SCORES_FILE = OUT_DIR / "_judge_scores.json"

JUDGE_PROMPT = """Ты строгий судья эффективности. Оцени OUTPUT по 10-балльной шкале.

КРИТЕРИИ (0-10 каждый):
- effectiveness: доставит ли обещанный результат?
- first_try_quality: можно ли использовать сразу?
- actionability: конкретные шаги сегодня?
- realistic_outcome: реалистично?
- completeness: все требования покрыты?

ШКАЛА:
- 10: лучший в мире, превзойдёт любое человеческое решение
- 9: отлично, лучше 95% решений
- 8: очень хорошо, мелкие пробелы
- 7: хорошо, требует доработки
- 6: средне
- ≤5: плохо

ОТВЕТ — валидный JSON (без markdown, без пояснений):
{"effectiveness": <0-10>, "first_try_quality": <0-10>, "actionability": <0-10>, "realistic_outcome": <0-10>, "completeness": <0-10>, "average": <float>, "verdict": "BEST_IN_WORLD|EXCELLENT|GOOD|NEEDS_WORK|POOR", "would_user_succeed": "yes|no|partially", "main_weakness": "одна короткая фраза", "improvement": "одно конкретное улучшение"}

Начни с { закончи }. Без другого текста."""


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

    print("Preloading Qwen2.5-7B as judge...")
    get_local_llm()
    print("Ready.\n")

    print("=" * 100)
    print(f"LOCAL JUDGE v2 (Qwen2.5-7B) {VERSION}")
    print("=" * 100)

    new_scores = list(scores)

    for entry in data:
        test_id = entry["id"]
        if "output" not in entry:
            continue
        if test_id in existing and "average" in existing[test_id].get("scores", {}):
            s = existing[test_id]["scores"]
            print(f"✓ {test_id} — CACHED avg={s['average']}")
            continue

        print(f"\n▶ {test_id}")
        user_msg = f"""TASK:
{entry.get('user_task', '')}

OUTPUT:
{entry['output'][:5000]}

Оцени OUTPUT. Ответ — только JSON."""

        result = call_local(JUDGE_PROMPT, user_msg, max_tokens=600)
        if not result["success"]:
            print(f"  ✗ FAILED: {result.get('error')}")
            new_entry = {"id": test_id, "scores": {"error": result.get("error")}}
            for i, s in enumerate(new_scores):
                if s.get("id") == test_id:
                    new_scores[i] = new_entry
                    break
            else:
                new_scores.append(new_entry)
            save_json(SCORES_FILE, new_scores)
            continue

        content = result["content"]
        print(f"  ✓ {len(content)} chars")

        try:
            clean = content.strip()
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
            print(f"  raw: {content[:300]}")
            new_entry = {"id": test_id, "scores": {"error": str(e), "raw": content[:1000]}}
            for i, s in enumerate(new_scores):
                if s.get("id") == test_id:
                    new_scores[i] = new_entry
                    break
            else:
                new_scores.append(new_entry)
            save_json(SCORES_FILE, new_scores)

    print("\n" + "=" * 100)
    print(f"{'Тест':<25} {'Eff':>4} {'1st':>4} {'Act':>4} {'Real':>5} {'Compl':>6} {'AVG':>5} {'Verdict':<18}")
    print("=" * 100)
    sum_avg = 0
    count = 0
    for entry in new_scores:
        s = entry.get("scores", {})
        if "average" in s:
            avg = s["average"]
            sum_avg += avg
            count += 1
            print(f"{entry['id']:<25} {s.get('effectiveness','?'):>4} {s.get('first_try_quality','?'):>4} {s.get('actionability','?'):>4} {s.get('realistic_outcome','?'):>5} {s.get('completeness','?'):>6} {avg:>5} {s.get('verdict','?'):<18}")
            if "main_weakness" in s:
                print(f"  ❌ {s['main_weakness']}")
            if "improvement" in s:
                print(f"  💡 {s['improvement']}")
        else:
            print(f"{entry['id']:<25} ERROR: {str(s.get('error','?'))[:50]}")
    print("=" * 100)
    if count:
        print(f"{'AVERAGE':<25} {'':>4} {'':>4} {'':>4} {'':>5} {'':>6} {round(sum_avg/count, 2):>5}")


if __name__ == "__main__":
    judge_all()
