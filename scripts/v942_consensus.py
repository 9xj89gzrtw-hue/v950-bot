#!/usr/bin/env python3
"""
v942_consensus.py — MULTI-MODEL CONSENSUS v9.42
=================================================
3 models vote on the answer. Majority wins. Disagreement → abstain.

Models:
1. z-ai SDK (glm-4-plus) — transformer LLM
2. Pollinations GPT-OSS-20B — different transformer family
3. Rule-based (lexical) — non-LLM, deterministic

Voting:
- 3/3 agree → HIGH confidence, return answer
- 2/3 agree → MEDIUM confidence, return majority answer
- 3 different → ABSTAIN (no consensus)

Use case: high-stakes factual questions where hallucination is costly.
Trade-off: 3x latency (parallel) or 3x cost (sequential).

Usage:
    python3 v942_consensus.py --prompt "What is the capital of France?"
    python3 v942_consensus.py --prompt "Is 2+2=4?" --parallel
"""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/home/z/my-project/scripts")


def query_zai(prompt, system=""):
    """Query z-ai SDK."""
    from v938_llm_client import call_zai_chat
    result = call_zai_chat(prompt, system)
    return {"answer": result["content"], "model": "glm-4-plus", "tokens": result["tokens"]}


def query_pollinations(prompt, system=""):
    """Query Pollinations."""
    from v938_llm_client import call_pollinations_chat
    result = call_pollinations_chat(prompt, system)
    return {"answer": result["content"], "model": "gpt-oss-20b", "tokens": result["tokens"]}


def query_rule_based(prompt, system=""):
    """Rule-based 'model' — lexical patterns + simple logic."""
    prompt_lower = prompt.lower().strip()
    answer = ""
    
    # Math patterns
    m = re.match(r"what is (\d+)\s*\+\s*(\d+)\??", prompt_lower)
    if m:
        answer = str(int(m.group(1)) + int(m.group(2)))
    m = re.match(r"what is (\d+)\s*-\s*(\d+)\??", prompt_lower)
    if m:
        answer = str(int(m.group(1)) - int(m.group(2)))
    m = re.match(r"what is (\d+)\s*[×x*]\s*(\d+)\??", prompt_lower)
    if m:
        answer = str(int(m.group(1)) * int(m.group(2)))
    m = re.match(r"what is (\d+)\s*/\s*(\d+)\??", prompt_lower)
    if m and int(m.group(2)) != 0:
        answer = str(int(m.group(1)) // int(m.group(2)))
    
    # Capital of X
    capitals = {
        "france": "Paris", "germany": "Berlin", "italy": "Rome",
        "spain": "Madrid", "russia": "Moscow", "japan": "Tokyo",
        "china": "Beijing", "usa": "Washington, D.C.", "uk": "London",
        "england": "London",
    }
    m = re.search(r"capital of (\w+)\??", prompt_lower)
    if m:
        country = m.group(1)
        if country in capitals:
            answer = capitals[country]
    
    # Is X true?
    m = re.match(r"is (.+) (true|correct|right)\??", prompt_lower)
    if m:
        # Simple: 2+2=4 is true
        stmt = m.group(1)
        if "2+2=4" in stmt.replace(" ", "") or "2 plus 2 is 4" in stmt:
            answer = "Yes"
        elif "2+2=5" in stmt.replace(" ", ""):
            answer = "No"
    
    if not answer:
        answer = "[ABSTAIN: rule-based cannot answer]"
    
    return {"answer": answer, "model": "rule-based", "tokens": 0}


def normalize_answer(text):
    """Normalize answer for comparison (lowercase, strip punctuation)."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    # Take first sentence/line
    text = text.split(".")[0].split("\n")[0].strip()
    # Limit to 50 chars for comparison
    return text[:50]


def get_consensus(prompt, system="", parallel=True, verbose=False):
    """
    Get consensus from 3 models.
    
    Returns:
        {
            "answer": str,
            "confidence": "HIGH" | "MEDIUM" | "ABSTAIN",
            "agreement": "3/3" | "2/3" | "0/3",
            "model_answers": {model: answer},
            "model_normalized": {model: normalized},
            "latency_sec": float,
            "tokens_total": int,
        }
    """
    start_time = time.time()
    models = [
        ("z-ai-glm4-plus", query_zai),
        ("pollinations-gpt-oss-20b", query_pollinations),
        ("rule-based", query_rule_based),
    ]
    
    model_answers = {}
    model_normalized = {}
    tokens_total = 0
    
    if parallel:
        # Run all 3 in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(fn, prompt, system): name for name, fn in models}
            for future in concurrent.futures.as_completed(futures):
                name = futures[future]
                try:
                    result = future.result()
                    model_answers[name] = result["answer"]
                    model_normalized[name] = normalize_answer(result["answer"])
                    tokens_total += result.get("tokens", 0)
                    if verbose:
                        print(f"[consensus] {name}: {result['answer'][:80]!r}", file=sys.stderr)
                except Exception as e:
                    model_answers[name] = f"[ERROR: {e}]"
                    model_normalized[name] = "[error]"
                    if verbose:
                        print(f"[consensus] {name} FAILED: {e}", file=sys.stderr)
    else:
        # Sequential
        for name, fn in models:
            try:
                result = fn(prompt, system)
                model_answers[name] = result["answer"]
                model_normalized[name] = normalize_answer(result["answer"])
                tokens_total += result.get("tokens", 0)
                if verbose:
                    print(f"[consensus] {name}: {result['answer'][:80]!r}", file=sys.stderr)
            except Exception as e:
                model_answers[name] = f"[ERROR: {e}]"
                model_normalized[name] = "[error]"
    
    # Vote
    normalized_answers = list(model_normalized.values())
    counter = Counter(normalized_answers)
    top_answer, top_count = counter.most_common(1)[0]
    
    if top_count == 3:
        confidence = "HIGH"
        agreement = "3/3"
        answer = model_answers[[k for k, v in model_normalized.items() if v == top_answer][0]]
    elif top_count == 2:
        confidence = "MEDIUM"
        agreement = "2/3"
        answer = model_answers[[k for k, v in model_normalized.items() if v == top_answer][0]]
    else:
        confidence = "ABSTAIN"
        agreement = "0/3"
        answer = "[ABSTAIN: models disagree]"
    
    latency = time.time() - start_time
    
    return {
        "answer": answer,
        "confidence": confidence,
        "agreement": agreement,
        "model_answers": model_answers,
        "model_normalized": model_normalized,
        "latency_sec": round(latency, 2),
        "tokens_total": tokens_total,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--system", default="")
    parser.add_argument("--parallel", action="store_true", default=True)
    parser.add_argument("--sequential", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    
    parallel = not args.sequential
    result = get_consensus(args.prompt, args.system, parallel=parallel, verbose=args.verbose)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
