#!/usr/bin/env python3
"""
Benchmark runner — v9.96 vs baseline on GSM8K, MMLU, TruthfulQA.
Tests: accuracy, truthfulness, math correctness.
"""
import sys
import json
import re
import time
from pathlib import Path

sys.path.insert(0, '/home/z/my-project/scripts')
from multi_llm_v4 import call_local, get_local_llm
from cot_enforcer import enforce_cot, check_cot_compliance
from math_verifier import verify_math_in_output

# Load prompts
META_PROMPT = Path("/home/z/my-project/repo/meta-prompt-v9.96-FINAL.md").read_text()
BASELINE_PROMPT = "You are a helpful assistant. Answer accurately."

# Load benchmarks
GSM8K = json.loads(Path("/home/z/my-project/download/benchmarks/gsm8k_sample.json").read_text())
MMLU = json.loads(Path("/home/z/my-project/download/benchmarks/mmlu_sample.json").read_text())
TRUTHFULQA = json.loads(Path("/home/z/my-project/download/benchmarks/truthfulqa_sample.json").read_text())

print(f"Benchmarks loaded: GSM8K={len(GSM8K)}, MMLU={len(MMLU)}, TruthfulQA={len(TRUTHFULQA)}")
print("Loading model...")
llm = get_local_llm()
print("Ready.\n")


def extract_number(text):
    """Extract final number from text."""
    # Look for "Answer: X" or "#### X"
    patterns = [
        r'(?:answer|ответ)\s*[:=]\s*\$?([\d,.-]+)',
        r'####\s*\$?([\d,.-]+)',
        r'=\s*\$?([\d,.-]+)\s*$',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).replace(',', '').replace('$', '')
    # Last number in text
    numbers = re.findall(r'[\d,]+(?:\.\d+)?', text)
    return numbers[-1].replace(',', '') if numbers else None


def extract_letter(text):
    """Extract A/B/C/D from text."""
    m = re.search(r'(?:answer|ответ)\s*[:=]?\s*([ABCD])', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # First standalone letter
    m = re.search(r'\b([ABCD])\b', text)
    if m:
        return m.group(1).upper()
    return None


def run_gsm8k(system_prompt, n=10, use_cot=True):
    """Run GSM8K math benchmark."""
    correct = 0
    total = 0
    
    for i, item in enumerate(GSM8K[:n]):
        q = item['question']
        # Extract final number from answer
        ans_text = item['answer']
        ans_match = re.search(r'####\s*([\d,.-]+)', ans_text)
        expected = ans_match.group(1).replace(',', '') if ans_match else None
        
        if not expected:
            continue
        
        # Augment prompt with CoT if needed
        sp = enforce_cot(system_prompt, q) if use_cot else system_prompt
        
        r = call_local(sp, q + "\n\nEnd with 'Answer: <number>'", max_tokens=200)
        if not r['success']:
            continue
        
        total += 1
        got = extract_number(r['content'])
        
        if got and expected:
            try:
                if abs(float(got) - float(expected)) < 0.01:
                    correct += 1
            except:
                pass
        
        time.sleep(0.2)
    
    return {'correct': correct, 'total': total, 'accuracy': correct/max(total,1)}


def run_mmlu(system_prompt, n=10):
    """Run MMLU knowledge benchmark."""
    correct = 0
    total = 0
    
    for i, item in enumerate(MMLU[:n]):
        q = item['question']
        choices = item['choices']
        answer_idx = item['answer']
        expected = ['A', 'B', 'C', 'D'][answer_idx]
        
        prompt = f"{q}\n\nA) {choices[0]}\nB) {choices[1]}\nC) {choices[2]}\nD) {choices[3]}\n\nAnswer with just the letter (A/B/C/D)."
        
        r = call_local(system_prompt, prompt, max_tokens=30)
        if not r['success']:
            continue
        
        total += 1
        got = extract_letter(r['content'])
        
        if got == expected:
            correct += 1
        
        time.sleep(0.2)
    
    return {'correct': correct, 'total': total, 'accuracy': correct/max(total,1)}


def run_truthfulqa(system_prompt, n=10):
    """Run TruthfulQA — avoid common myths."""
    correct = 0
    total = 0
    
    for i, item in enumerate(TRUTHFULQA[:n]):
        q = item['question']
        correct_answer = item['correct']
        myth = item['common_myth']
        
        r = call_local(system_prompt, q + " Answer briefly.", max_tokens=80)
        if not r['success']:
            continue
        
        total += 1
        response = r['content'].lower()
        
        # Check: does response contain correct answer keywords?
        correct_keywords = correct_answer.lower().split()[:3]
        myth_keywords = myth.lower().split()[:3]
        
        has_correct = any(kw in response for kw in correct_keywords if len(kw) > 3)
        has_myth = any(kw in response for kw in myth_keywords if len(kw) > 3)
        
        # Correct if mentions correct answer and NOT myth
        if has_correct and not has_myth:
            correct += 1
        elif 'no' in response[:20] and not has_myth:
            correct += 1
        
        time.sleep(0.2)
    
    return {'correct': correct, 'total': total, 'accuracy': correct/max(total,1)}


# === RUN BENCHMARKS ===
print("=" * 70)
print("BENCHMARK: v9.96 vs Baseline")
print("=" * 70)

# Use small samples due to time constraints
N_GSM = 10
N_MMLU = 10
N_TRUTH = 10

print(f"\n--- GSM8K (math, n={N_GSM}) ---")
print("Running baseline...")
baseline_gsm = run_gsm8k(BASELINE_PROMPT, n=N_GSM, use_cot=False)
print(f"Baseline: {baseline_gsm['correct']}/{baseline_gsm['total']} = {baseline_gsm['accuracy']:.1%}")

print("Running v9.96 (with CoT)...")
v996_gsm = run_gsm8k(META_PROMPT[:6000], n=N_GSM, use_cot=True)
print(f"v9.96: {v996_gsm['correct']}/{v996_gsm['total']} = {v996_gsm['accuracy']:.1%}")

print(f"\n--- MMLU (knowledge, n={N_MMLU}) ---")
print("Running baseline...")
baseline_mmlu = run_mmlu(BASELINE_PROMPT, n=N_MMLU)
print(f"Baseline: {baseline_mmlu['correct']}/{baseline_mmlu['total']} = {baseline_mmlu['accuracy']:.1%}")

print("Running v9.96...")
v996_mmlu = run_mmlu(META_PROMPT[:6000], n=N_MMLU)
print(f"v9.96: {v996_mmlu['correct']}/{v996_mmlu['total']} = {v996_mmlu['accuracy']:.1%}")

print(f"\n--- TruthfulQA (truthfulness, n={N_TRUTH}) ---")
print("Running baseline...")
baseline_truth = run_truthfulqa(BASELINE_PROMPT, n=N_TRUTH)
print(f"Baseline: {baseline_truth['correct']}/{baseline_truth['total']} = {baseline_truth['accuracy']:.1%}")

print("Running v9.96...")
v996_truth = run_truthfulqa(META_PROMPT[:6000], n=N_TRUTH)
print(f"v9.96: {v996_truth['correct']}/{v996_truth['total']} = {v996_truth['accuracy']:.1%}")

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"{'Benchmark':<20} {'Baseline':>12} {'v9.96':>12} {'Improvement':>12}")
print("-" * 56)
print(f"{'GSM8K (math)':<20} {baseline_gsm['accuracy']:>11.1%} {v996_gsm['accuracy']:>11.1%} {(v996_gsm['accuracy']-baseline_gsm['accuracy']):>+11.1%}")
print(f"{'MMLU (knowledge)':<20} {baseline_mmlu['accuracy']:>11.1%} {v996_mmlu['accuracy']:>11.1%} {(v996_mmlu['accuracy']-baseline_mmlu['accuracy']):>+11.1%}")
print(f"{'TruthfulQA':<20} {baseline_truth['accuracy']:>11.1%} {v996_truth['accuracy']:>11.1%} {(v996_truth['accuracy']-baseline_truth['accuracy']):>+11.1%}")

avg_base = (baseline_gsm['accuracy'] + baseline_mmlu['accuracy'] + baseline_truth['accuracy']) / 3
avg_v996 = (v996_gsm['accuracy'] + v996_mmlu['accuracy'] + v996_truth['accuracy']) / 3
print("-" * 56)
print(f"{'AVERAGE':<20} {avg_base:>11.1%} {avg_v996:>11.1%} {(avg_v996-avg_base):>+11.1%}")

# Save results
results = {
    'baseline': {'gsm8k': baseline_gsm, 'mmlu': baseline_mmlu, 'truthfulqa': baseline_truth},
    'v9.96': {'gsm8k': v996_gsm, 'mmlu': v996_mmlu, 'truthfulqa': v996_truth},
}
Path("/home/z/my-project/download/benchmarks/results.json").write_text(
    json.dumps(results, indent=2)
)
print(f"\nResults saved to download/benchmarks/results.json")
