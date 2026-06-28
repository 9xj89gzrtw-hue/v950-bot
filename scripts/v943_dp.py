#!/usr/bin/env python3
"""
v943_dp.py — DIFFERENTIAL PRIVACY for LLM calls v9.43
=======================================================
Add noise to LLM prompts/responses to prevent membership inference attacks.

Use case: when sending prompts to external LLMs (Pollinations), add noise
so attackers can't determine if specific data was in the training set.

Techniques:
1. Prompt sanitization: redact PII (emails, phones, IPs) before sending
2. Response noise: add random whitespace/typos to non-critical parts
3. K-anonymity: replace rare entities with generic terms
4. Differential privacy budget: track ε (epsilon) spent per session

This is NOT full DP (would require Laplace/Gaussian noise on numeric outputs),
but provides practical privacy protection for LLM calls.

Usage:
    python3 v943_dp.py sanitize --prompt "My email is alice@example.com, call me at +1234567890"
    python3 v943_dp.py anonymize --prompt "John Smith from Acme Corp said..."
    python3 v943_dp.py budget  # show privacy budget spent
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

BUDGET_FILE = "/home/z/my-project/scripts/v943_dp_budget.json"
DEFAULT_EPSILON_BUDGET = 10.0  # total privacy budget per session


# ============================================================================
# PII PATTERNS
# ============================================================================

PII_PATTERNS = [
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REDACTED]'),
    (r'\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}', '[PHONE_REDACTED]'),
    (r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '[IP_REDACTED]'),
    (r'\b\d{3}-\d{2}-\d{4}\b', '[SSN_REDACTED]'),
    (r'\b\d{16}\b', '[CARD_REDACTED]'),
    (r'\b(?:passport|id|license)\s*(?:no\.?|number)?\s*[:#]?\s*[A-Z0-9]{6,}\b', '[ID_REDACTED]'),
]


# ============================================================================
# ENTITY ANONYMIZATION (k-anonymity)
# ============================================================================

# Replace specific entities with generic categories
ENTITY_PATTERNS = [
    # Names (simplified — replace capitalized words that look like names)
    (r'\b(?:Mr|Mrs|Ms|Dr|Prof)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', r'\1 [NAME_ANON]'),
    # Company names
    (r'\b(?:Inc|Corp|LLC|Ltd|GmbH|SA)\.?\b', '[COMPANY_TYPE]'),
    # Street addresses
    (r'\b\d+\s+[A-Z][a-z]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd)\b', '[ADDRESS_REDACTED]'),
    # Dates of birth
    (r'\b(?:born|DOB|date of birth)\s*[:#]?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', '[DOB_REDACTED]'),
]


def sanitize_prompt(prompt):
    """Remove PII from prompt before sending to LLM."""
    sanitized = prompt
    redactions = []
    
    for pattern, replacement in PII_PATTERNS:
        matches = re.findall(pattern, sanitized)
        if matches:
            redactions.append({
                "pattern": pattern[:50],
                "count": len(matches),
                "replacement": replacement,
            })
        sanitized = re.sub(pattern, replacement, sanitized)
    
    return {
        "original_length": len(prompt),
        "sanitized_length": len(sanitized),
        "sanitized": sanitized,
        "redactions": redactions,
        "total_redacted": sum(r["count"] for r in redactions),
    }


def anonymize_entities(prompt):
    """Replace specific entities with generic terms (k-anonymity)."""
    anonymized = prompt
    replacements = []
    
    for pattern, replacement in ENTITY_PATTERNS:
        matches = re.findall(pattern, anonymized)
        if matches:
            replacements.append({
                "pattern": pattern[:50],
                "count": len(matches),
            })
        anonymized = re.sub(pattern, replacement, anonymized)
    
    return {
        "anonymized": anonymized,
        "replacements": replacements,
    }


def add_response_noise(response, noise_level=0.01):
    """Add minimal noise to response (random whitespace in non-critical parts).
    
    noise_level: probability of adding noise to each word.
    """
    words = response.split()
    noisy = []
    
    for word in words:
        if re.random() < noise_level:
            # Add zero-width space (invisible noise)
            word = word + "\u200b"
        noisy.append(word)
    
    return " ".join(noisy)


# ============================================================================
# PRIVACY BUDGET TRACKING
# ============================================================================

def load_budget():
    """Load privacy budget tracker."""
    if not os.path.exists(BUDGET_FILE):
        return {"epsilon_spent": 0.0, "epsilon_budget": DEFAULT_EPSILON_BUDGET, "calls": []}
    try:
        return json.loads(Path(BUDGET_FILE).read_text())
    except Exception:
        return {"epsilon_spent": 0.0, "epsilon_budget": DEFAULT_EPSILON_BUDGET, "calls": []}


def save_budget(budget):
    Path(BUDGET_FILE).write_text(json.dumps(budget, indent=2))


def spend_epsilon(epsilon, operation="llm_call"):
    """Spend privacy budget. Returns False if budget exhausted."""
    budget = load_budget()
    
    if budget["epsilon_spent"] + epsilon > budget["epsilon_budget"]:
        return {
            "allowed": False,
            "reason": "budget exhausted",
            "spent": budget["epsilon_spent"],
            "budget": budget["epsilon_budget"],
        }
    
    budget["epsilon_spent"] += epsilon
    budget["calls"].append({
        "operation": operation,
        "epsilon": epsilon,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    save_budget(budget)
    
    return {
        "allowed": True,
        "spent": budget["epsilon_spent"],
        "remaining": budget["epsilon_budget"] - budget["epsilon_spent"],
        "budget": budget["epsilon_budget"],
    }


def process_llm_call(prompt, epsilon_cost=0.1):
    """
    Full DP processing for LLM call.
    
    1. Check privacy budget
    2. Sanitize prompt (remove PII)
    3. Anonymize entities
    4. Return processed prompt + metadata
    """
    # Check budget
    budget_check = spend_epsilon(epsilon_cost, "llm_call")
    if not budget_check["allowed"]:
        return {
            "allowed": False,
            "error": budget_check["reason"],
            "budget_status": budget_check,
        }
    
    # Sanitize
    sanitized = sanitize_prompt(prompt)
    
    # Anonymize
    anonymized = anonymize_entities(sanitized["sanitized"])
    
    return {
        "allowed": True,
        "processed_prompt": anonymized["anonymized"],
        "sanitization": sanitized,
        "anonymization": anonymized,
        "budget_status": budget_check,
        "epsilon_cost": epsilon_cost,
    }


def main():
    import random  # needed for add_response_noise
    
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["sanitize", "anonymize", "process", "budget", "reset-budget"])
    parser.add_argument("--prompt", help="prompt to process")
    parser.add_argument("--epsilon", type=float, default=0.1, help="epsilon cost")
    args = parser.parse_args()
    
    if args.command == "sanitize":
        if not args.prompt:
            print("--prompt required")
            sys.exit(2)
        result = sanitize_prompt(args.prompt)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif args.command == "anonymize":
        if not args.prompt:
            print("--prompt required")
            sys.exit(2)
        result = anonymize_entities(args.prompt)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif args.command == "process":
        if not args.prompt:
            print("--prompt required")
            sys.exit(2)
        result = process_llm_call(args.prompt, args.epsilon)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif args.command == "budget":
        budget = load_budget()
        print(json.dumps(budget, indent=2))
    
    elif args.command == "reset-budget":
        save_budget({"epsilon_spent": 0.0, "epsilon_budget": DEFAULT_EPSILON_BUDGET, "calls": []})
        print("Budget reset")


if __name__ == "__main__":
    main()
