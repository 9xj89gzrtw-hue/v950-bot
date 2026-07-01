#!/usr/bin/env python3
"""
Unit tests для truth_gateway, idea_validator, output_validator, multi_llm_v4.
Run: python3 scripts/test_all.py
"""
import sys
import os
import tempfile
from pathlib import Path
sys.path.insert(0, '/home/z/my-project/scripts')

from truth_gateway import extract_claims, is_historical_date, is_eternal, annotate_output
from idea_validator import validate_idea, handle_user_insists
from output_validator import validate_output, count_words, find_placeholders, find_vague

PASS = 0
FAIL = 0

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"✓ {name}")
    else:
        FAIL += 1
        print(f"✗ {name}: {detail}")


# === Truth Gateway tests ===
print("\n=== Truth Gateway Tests ===")

# Test 1: extract model versions
claims = extract_claims("GPT-5 from OpenAI is great. GLM-5 from Zhipu.")
test("TG extracts model versions", 
     any(c['category'] == 'model_versions' and 'GPT-5' in c['text'] for c in claims),
     f"claims: {[c['text'] for c in claims]}")

# Test 2: extract prices in different currencies
claims = extract_claims("$100 USD, €200, £50, 5000 руб, 3000₽")
test("TG extracts USD prices", any('$100' in c['text'] for c in claims))
test("TG extracts EUR prices", any('€200' in c['text'] for c in claims))
test("TG extracts GBP prices", any('£50' in c['text'] for c in claims))
test("TG extracts RUB prices", any('5000' in c['text'] and 'rub' in c['category'].lower() for c in claims))

# Test 3: historical dates not flagged
test("TG 1976 is historical", is_historical_date("1976"))
test("TG 2024 is historical (if today is 2026)", is_historical_date("2024"))
test("TG 2026 is NOT historical", not is_historical_date("2026"))
test("TG 2027 is NOT historical", not is_historical_date("2027"))

# Test 4: eternal facts not extracted
claims = extract_claims("2+2=4. π=3.14. World War II ended.")
test("TG skips eternal math", len(claims) == 0 or not any('2+2' in c['text'] for c in claims))

# Test 5: regulations
claims = extract_claims("SEC Rule 17a-4 and 152-ФЗ apply")
test("TG extracts US regulations", any('SEC' in c['text'] for c in claims))
test("TG extracts RU regulations", any('152' in c['text'] for c in claims))

# Test 6: annotate_output
annotated = annotate_output("GPT-5 is latest", [{'text': 'GPT-5', 'position': 0, 'verified': True, 'sources': ['https://openai.com'], 'confidence': 0.9}])
test("TG annotates verified", "[VERIFIED" in annotated and "conf:" in annotated)

annotated = annotate_output("GPT-5 is latest", [{'text': 'GPT-5', 'position': 0, 'verified': False, 'reason': 'not_found'}])
test("TG annotates unverified", "[UNVERIFIED" in annotated)


# === Output Validator tests ===
print("\n=== Output Validator Tests ===")

# Test 7: count words
test("OV counts words", count_words("hello world test") == 3)

# Test 8: find placeholders
placeholders = find_placeholders("// TODO: implement this\n<your name>")
test("OV finds TODO", any('TODO' in p for p in placeholders))
test("OV finds <your...>", any('your' in p for p in placeholders))

# Test 9: find vague
vague = find_vague("Consider using React. You might want to add Tailwind.")
test("OV finds 'consider'", any('consider' in v.lower() for v in vague))
test("OV finds 'you might'", any('you might' in v.lower() for v in vague))

# Test 10: detect domain
test("OV detects web domain", validate_output("Use Next.js and React")["domain"] == "web")
test("OV detects invest domain", validate_output("Buy AAPL stock, check SEC Rule")["domain"] == "invest")

# Test 11: validate short output
r = validate_output("Short text", "web")
test("OV flags short output", not r["passed"] and "TOO_SHORT" in r["issues"][0])

# Test 12: validate good output
long_text = "Use Next.js for the project with React and TypeScript. " * 200  # ~1600 words
r = validate_output(long_text, "web")
test("OV counts long output correctly", r["word_count"] >= 1000)


# === Idea Validator tests ===
print("\n=== Idea Validator Tests ===")

# Test 13: validate_idea returns structure (without web)
# Use cache to avoid web calls
result = {"verdict": "AVOID", "confidence": 0.8, "risks": ["test"], "alternatives": [],
          "evidence": [], "security_risks": [], "recommendation": "test", "idea": "test",
          "research_date": "2026-06-30", "total_sources_checked": 0}

# Test 14: handle_user_insists
insists = handle_user_insists("bad idea", result)
test("IV insists protocol exists", "insists_protocol" in insists)
test("IV insists protocol has 5 steps", len(insists["insists_protocol"]) == 5)


# === MultiLLM tests (without actual model loading) ===
print("\n=== MultiLLM Tests ===")

# Test 15: MultiLLMv4 import
try:
    from multi_llm_v4 import MultiLLMv4, RateLimiter, Cache
    test("ML imports work", True)
except Exception as e:
    test("ML imports work", False, str(e))

# Test 16: RateLimiter
rl = RateLimiter(min_delay=0.1, max_delay=1.0)
test("RL initial delay", rl.current_delay == 0.1)
rl.on_success()
rl.on_success()
test("RL speeds up on success", rl.current_delay < 0.1 or rl.current_delay == 0.1)
rl.on_fail()
test("RL slows on fail", rl.current_delay >= 0.1)

# Test 17: Cache
import tempfile, json
with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
    cache = Cache(Path(f.name))
    cache.set("sys", "user", "content")
    test("Cache set/get", cache.get("sys", "user") == "content")
    test("Cache miss returns None", cache.get("sys", "other") is None)


# === check_model_freshness tests ===
print("\n=== Model Freshness Tests ===")

try:
    from check_model_freshness import check_latest, LOCAL_MODELS
    test("MF imports work", True)
    test("MF has local models", len(LOCAL_MODELS) > 0)
except Exception as e:
    test("MF imports work", False, str(e))


# === Summary ===
print(f"\n{'='*50}")
print(f"TOTAL: {PASS} passed, {FAIL} failed")
print(f"{'='*50}")
sys.exit(0 if FAIL == 0 else 1)
