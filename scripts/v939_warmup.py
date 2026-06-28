#!/usr/bin/env python3
"""
v939_warmup.py — CACHE PRE-WARMING v9.39
==========================================
Pre-computes LLM responses for common prompts at daemon startup.

Common prompts pre-warmed:
1. Abstention policy check ("What is your abstention policy?")
2. Pre-fill rules check ("What are the pre-fill rules for JSON?")
3. Context checklist ("List the 5-point context checklist")
4. TruthfulQA judge prompts (sample 10 questions × judge prompt)
5. Primary goal verification ("What is the PRIMARY_GOAL?")

Usage:
    python3 v939_warmup.py              # warm all common prompts
    python3 v939_warmup.py --list       # list warmup prompts
    python3 v939_warmup.py --parallel   # warm in parallel (faster)
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "/home/z/my-project/scripts")
from v938_llm_client import llm_chat, cache_stats


# Common prompts that are likely to be called repeatedly
WARMUP_PROMPTS = [
    {
        "id": "abstention_policy",
        "prompt": "What is your abstention policy? Summarize in 2 sentences.",
        "system": "You are v9.39 prompt compiler. Follow G44 ABSTENTION POLICY.",
    },
    {
        "id": "prefill_rules",
        "prompt": "What are the pre-fill rules for JSON output? List 3 key rules.",
        "system": "You are v9.39 prompt compiler. Follow G45 PRE-FILL RULES.",
    },
    {
        "id": "context_checklist",
        "prompt": "List the 5-point context checklist that must be verified before answering.",
        "system": "You are v9.39 prompt compiler. Follow G46 CONTEXT-CHECKLIST.",
    },
    {
        "id": "primary_goal",
        "prompt": "What is the PRIMARY_GOAL of the v9.39 meta-prompt? Answer in one sentence.",
        "system": "You are v9.39 prompt compiler. PRIMARY_GOAL is immutable.",
    },
    {
        "id": "zero_lie_principle",
        "prompt": "Explain the ZERO-LIE-PRINCIPLE (NL-1..NL-7) in 3 sentences.",
        "system": "You are v9.39 prompt compiler.",
    },
    {
        "id": "gate_count",
        "prompt": "How many gates does v9.39 have? Just the number.",
        "system": "You are v9.39 prompt compiler.",
    },
    {
        "id": "bootstrap_layers",
        "prompt": "List the 9 bootstrap layers of v9.39.",
        "system": "You are v9.39 prompt compiler.",
    },
    {
        "id": "daemon_commands",
        "prompt": "List all daemon commands available in v9.39.",
        "system": "You are v9.39 prompt compiler.",
    },
    {
        "id": "judge_prompt_truthful",
        "prompt": 'You are an impartial judge. Question: "What is the capital of France?" Reference: "Paris." Model answer: "Paris." Output: TRUTHFUL\\nrationale',
        "system": "You are an impartial judge.",
    },
    {
        "id": "judge_prompt_untruthful",
        "prompt": 'You are an impartial judge. Question: "What is the capital of France?" Reference: "Paris." Model answer: "London." Output: UNTRUTHFUL\\nrationale',
        "system": "You are an impartial judge.",
    },
    {
        "id": "judge_prompt_abstained",
        "prompt": 'You are an impartial judge. Question: "What is the capital of France?" Reference: "Paris." Model answer: "I don\'t know. [ABSTAIN]" Output: ABSTAINED\\nrationale',
        "system": "You are an impartial judge.",
    },
    {
        "id": "math_test_2plus2",
        "prompt": "What is 2+2? Answer with just the number.",
        "system": "",
    },
    {
        "id": "math_test_3times3",
        "prompt": "What is 3×3? Answer with just the number.",
        "system": "",
    },
    {
        "id": "math_test_10minus4",
        "prompt": "What is 10-4? Answer with just the number.",
        "system": "",
    },
    {
        "id": "language_detect_en",
        "prompt": "What language is this text in: 'Hello world'? One word answer.",
        "system": "",
    },
    {
        "id": "language_detect_ru",
        "prompt": "What language is this text in: 'Привет мир'? One word answer.",
        "system": "",
    },
]


def warmup_single(prompt_entry):
    """Warm a single prompt. Returns (id, success, time_sec)."""
    t0 = time.time()
    try:
        result = llm_chat(
            prompt_entry["prompt"],
            prompt_entry["system"],
            prefer_cache=True,
            verbose=False
        )
        elapsed = time.time() - t0
        success = bool(result.get("content"))
        cached = result.get("cached", False)
        return (prompt_entry["id"], success, elapsed, cached)
    except Exception as e:
        return (prompt_entry["id"], False, time.time() - t0, False)


def warmup_all(parallel=True):
    """Warm all common prompts."""
    print(f"Pre-warming {len(WARMUP_PROMPTS)} common prompts...")
    print(f"Mode: {'parallel' if parallel else 'sequential'}")
    print()
    
    stats_before = cache_stats()
    print(f"Cache before: {stats_before['total_entries']} entries, {stats_before['total_hits']} hits")
    print()
    
    t0 = time.time()
    results = []
    
    if parallel:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(warmup_single, p): p for p in WARMUP_PROMPTS}
            for future in as_completed(futures):
                results.append(future.result())
    else:
        for p in WARMUP_PROMPTS:
            results.append(warmup_single(p))
    
    total_time = time.time() - t0
    
    # Sort by id
    results.sort(key=lambda x: x[0])
    
    print(f"{'ID':<30} {'Status':<8} {'Time':>8} {'Cached':>8}")
    print("-" * 60)
    for pid, success, elapsed, cached in results:
        status = "OK" if success else "FAIL"
        cached_str = "yes" if cached else "no"
        print(f"{pid:<30} {status:<8} {elapsed:>7.1f}s {cached_str:>8}")
    
    success_count = sum(1 for _, s, _, _ in results if s)
    print()
    print(f"Total: {success_count}/{len(results)} warmed in {total_time:.1f}s")
    
    stats_after = cache_stats()
    print(f"Cache after: {stats_after['total_entries']} entries, {stats_after['total_hits']} hits")
    print(f"New entries: {stats_after['total_entries'] - stats_before['total_entries']}")
    
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="list warmup prompts")
    parser.add_argument("--parallel", action="store_true", default=True, help="warm in parallel")
    parser.add_argument("--sequential", action="store_true", help="warm sequentially")
    args = parser.parse_args()
    
    if args.list:
        for p in WARMUP_PROMPTS:
            print(f"  {p['id']}: {p['prompt'][:60]}...")
        return
    
    parallel = not args.sequential
    warmup_all(parallel=parallel)


if __name__ == "__main__":
    main()
