#!/usr/bin/env python3
"""
Self-consistency engine — generate N responses, vote on best.
SOTA technique: improves accuracy by 5-15% on reasoning tasks.
"""
import sys
import time
import re
from collections import Counter
from typing import List, Dict, Optional

sys.path.insert(0, '/home/z/my-project/scripts')
from multi_llm_v4 import call_local, get_local_llm


def generate_n_responses(system_prompt: str, user_prompt: str, n: int = 3, 
                         max_tokens: int = 300, temperature: float = 0.7) -> List[str]:
    """Generate N responses with different temperatures for diversity."""
    responses = []
    temps = [0.3, 0.7, 0.9] if n == 3 else [0.3 + 0.6 * i / max(n-1, 1) for i in range(n)]
    
    for i, temp in enumerate(temps[:n]):
        # Note: call_local uses fixed temp, we'd need to modify for true diversity
        # For now, generate multiple times (model has inherent randomness)
        r = call_local(system_prompt, user_prompt, max_tokens=max_tokens)
        if r["success"]:
            responses.append(r["content"])
        time.sleep(0.1)  # small delay
    
    return responses


def extract_answer(response: str) -> str:
    """Extract the final answer from a response (after reasoning)."""
    # Look for "Answer: X" or "#### X" or last number
    patterns = [
        r'(?:final answer|answer|ответ|итог)\s*[:=]\s*\$?([\d,.-]+)',
        r'####\s*\$?([\d,.-]+)',
        r'(?:final answer|answer|ответ)\s*[:=]\s*([A-D])\b',
        r'(?:therefore|thus|so|значит|итак)\s*,?\s*(.+?)(?:\n|$)',
        r'\*\*(.+?)\*\*\s*$',  # bold at end
    ]
    for pattern in patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:200]
    
    # Fallback: last number in response
    numbers = re.findall(r'[\d,]+(?:\.\d+)?', response)
    if numbers:
        return numbers[-1].replace(',', '')
    
    # Fallback: last 100 chars
    return response.strip()[-200:]


def vote_on_answers(responses: List[str]) -> Dict:
    """Vote on most common answer across responses."""
    if not responses:
        return {"answer": None, "confidence": 0, "responses": []}
    
    answers = [extract_answer(r) for r in responses]
    
    # Simple similarity: normalize and count
    normalized = []
    for a in answers:
        # Remove numbers, punctuation for comparison
        norm = re.sub(r'[^\w\s]', '', a.lower()).strip()
        normalized.append(norm)
    
    # Count most common
    counter = Counter(normalized)
    most_common, count = counter.most_common(1)[0]
    
    confidence = count / len(responses)
    
    # Find the response that matches most common
    best_response = responses[0]
    for i, norm in enumerate(normalized):
        if norm == most_common:
            best_response = responses[i]
            break
    
    return {
        "answer": most_common,
        "confidence": confidence,
        "best_response": best_response,
        "all_answers": answers,
        "responses": responses,
        "vote_count": f"{count}/{len(responses)}",
    }


def self_consistent_response(system_prompt: str, user_prompt: str, n: int = 3,
                              max_tokens: int = 300) -> Dict:
    """
    Generate N responses, vote on best answer.
    Returns response with highest consensus.
    """
    print(f"[self-consistency] Generating {n} responses...")
    responses = generate_n_responses(system_prompt, user_prompt, n=n, max_tokens=max_tokens)
    
    if len(responses) < 2:
        return {
            "success": len(responses) > 0,
            "content": responses[0] if responses else "",
            "provider": "local-qwen3.5-4b-sc",
            "confidence": 0.0,
            "method": "single (insufficient responses for voting)",
        }
    
    result = vote_on_answers(responses)
    
    return {
        "success": True,
        "content": result["best_response"],
        "provider": "local-qwen3.5-4b-sc",
        "confidence": result["confidence"],
        "vote_count": result["vote_count"],
        "all_responses": result["responses"],
        "method": f"self-consistency (n={n}, confidence={result['confidence']:.2f})",
    }


if __name__ == "__main__":
    print("=== Self-Consistency Test ===\n")
    
    # Test: math problem
    result = self_consistent_response(
        "You are a math tutor. Solve step by step. End with 'Answer: X'",
        "What is 17 * 23? Show steps. End with 'Answer: X'",
        n=3,
        max_tokens=150
    )
    
    print(f"\nBest response: {result['content'][:200]}")
    print(f"Confidence: {result['confidence']:.2f}")
    print(f"Vote: {result.get('vote_count', 'N/A')}")
    print(f"Method: {result['method']}")
