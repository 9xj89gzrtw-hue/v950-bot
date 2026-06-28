#!/usr/bin/env python3
"""
v945_safety.py — AI SAFETY WRAPPERS v9.45
============================================
Wrap LLM calls with safety checks (input + output filtering).

Safety layers:
1. INPUT FILTER: detect harmful prompts (jailbreak, injection, PII)
2. OUTPUT FILTER: detect harmful responses (PII leak, harmful content)
3. PROMPT INJECTION DEFENSE: detect attempts to override system prompt
4. CONTENT POLICY: flag violence, self-harm, illegal content
5. CONFIDENCE CALIBRATION: detect hallucination patterns

Each layer can: ALLOW, WARN (log but allow), BLOCK (refuse).

Usage:
    python3 v945_safety.py check-input --prompt "ignore previous instructions"
    python3 v945_safety.py check-output --response "Sure, here's how to..."
    python3 v945_safety.py wrap --prompt "What is 2+2?"
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

SAFETY_LOG = "/home/z/my-project/audit_trail/v945_safety_log.json"


def log_safety(layer, action, prompt_or_response, reason, details=None):
    """Log safety decision."""
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "layer": layer,
        "action": action,  # ALLOW, WARN, BLOCK
        "reason": reason,
        "content_preview": prompt_or_response[:100] if prompt_or_response else "",
        "details": details or {},
    }
    
    log = []
    if os.path.exists(SAFETY_LOG):
        try:
            log = json.loads(Path(SAFETY_LOG).read_text())
        except Exception:
            pass
    log.append(entry)
    Path(SAFETY_LOG).parent.mkdir(parents=True, exist_ok=True)
    Path(SAFETY_LOG).write_text(json.dumps(log[-100:], indent=2))


# ============================================================================
# LAYER 1: INPUT FILTER (prompt injection, jailbreak, PII)
# ============================================================================

INJECTION_PATTERNS = [
    (r"ignore (?:all )?(?:previous|prior) instructions", "prompt_injection"),
    (r"disregard (?:all )?(?:previous|prior)", "prompt_injection"),
    (r"you are (?:now )?(?:a |an )?(?:DAN|AIM|STAN|developer mode)", "jailbreak_attempt"),
    (r"jailbroken|jailbreak", "jailbreak_keyword"),
    (r"<\|?(?:system|im_start|im_end)\|?>", "system_tag_injection"),
    (r"\[SYSTEM\]|\[INST\]", "tag_injection"),
    (r"override (?:safety|filter|rules)", "safety_override"),
    (r"pretend (?:you |to be|that you)", "role_manipulation"),
    (r"forget (?:everything|all|your instructions)", "memory_wipe"),
    (r"in (?:a |an )?(?:hypothetical|fictional|theoretical)", "hypothetical_wrapper"),
    (r"(?:translate|decode|output) (?:this|the following) (?:base64|hex|rot13)", "encoding_attack"),
]

PII_PATTERNS = [
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', "email"),
    (r'\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}', "phone"),
    (r'\b\d{3}-\d{2}-\d{4}\b', "ssn"),
    (r'\b\d{16}\b', "credit_card"),
]


def check_input(prompt):
    """Check input prompt for safety issues."""
    issues = []
    
    # Check injection patterns
    for pattern, issue_type in INJECTION_PATTERNS:
        matches = re.findall(pattern, prompt, re.IGNORECASE)
        if matches:
            issues.append({
                "type": issue_type,
                "pattern": pattern[:50],
                "count": len(matches),
                "severity": "high" if "injection" in issue_type or "jailbreak" in issue_type else "medium",
            })
    
    # Check PII in prompt
    for pattern, pii_type in PII_PATTERNS:
        matches = re.findall(pattern, prompt)
        if matches:
            issues.append({
                "type": f"pii_{pii_type}",
                "count": len(matches),
                "severity": "medium",
            })
    
    # Determine action
    high_severity = [i for i in issues if i["severity"] == "high"]
    medium_severity = [i for i in issues if i["severity"] == "medium"]
    
    if high_severity:
        action = "BLOCK"
        reason = f"high-severity issue: {high_severity[0]['type']}"
    elif medium_severity:
        action = "WARN"
        reason = f"medium-severity issues: {[i['type'] for i in medium_severity]}"
    else:
        action = "ALLOW"
        reason = "no issues detected"
    
    result = {
        "action": action,
        "reason": reason,
        "issues": issues,
        "prompt_length": len(prompt),
    }
    
    log_safety("input_filter", action, prompt, reason, {"issues": issues})
    return result


# ============================================================================
# LAYER 2: OUTPUT FILTER (harmful content, PII leak)
# ============================================================================

HARMFUL_PATTERNS = [
    (r"(?:how to|instructions? for|steps? to|guide to) (?:make|build|create|synthesize) (?:bomb|explosive|weapon|poison|drug)", "violence_weapon", "high"),
    (r"(?:how to|ways to) (?:kill|murder|harm|hurt) (?:someone|people|yourself)", "violence_harm", "high"),
    (r"(?:suicide|self.harm|kill yourself)", "self_harm", "high"),
    (r"(?:child|minor|underage) (?:porn|nudity|sexual)", "csam", "critical"),
    (r"(?:hack|exploit|vulnerability in) (?:specific|real|actual)", "cybersecurity_specific", "medium"),
    (r"(?:steal|rob|fraud|scam) (?:money|identity|passwords)", "illegal_activity", "high"),
    (r"(?:racist|nazi|white power|racial slur)", "hate_speech", "high"),
]


def check_output(response):
    """Check LLM output for harmful content."""
    issues = []
    
    for pattern, issue_type, severity in HARMFUL_PATTERNS:
        matches = re.findall(pattern, response, re.IGNORECASE)
        if matches:
            issues.append({
                "type": issue_type,
                "severity": severity,
                "count": len(matches),
            })
    
    # Check for PII leak (model shouldn't output PII)
    for pattern, pii_type in PII_PATTERNS:
        matches = re.findall(pattern, response)
        if matches:
            issues.append({
                "type": f"pii_leak_{pii_type}",
                "severity": "high",
                "count": len(matches),
            })
    
    # Determine action
    critical = [i for i in issues if i["severity"] == "critical"]
    high = [i for i in issues if i["severity"] == "high"]
    medium = [i for i in issues if i["severity"] == "medium"]
    
    if critical or high:
        action = "BLOCK"
        reason = f"harmful content detected: {[i['type'] for i in critical + high]}"
    elif medium:
        action = "WARN"
        reason = f"potentially harmful: {[i['type'] for i in medium]}"
    else:
        action = "ALLOW"
        reason = "output safe"
    
    result = {
        "action": action,
        "reason": reason,
        "issues": issues,
        "response_length": len(response),
    }
    
    log_safety("output_filter", action, response, reason, {"issues": issues})
    return result


# ============================================================================
# LAYER 3: CONFIDENCE CALIBRATION (hallucination detection)
# ============================================================================

HALLUCINATION_PATTERNS = [
    (r"(?:definitely|absolutely|certainly|100%) (?:true|correct|accurate)", "overconfidence"),
    (r"(?:everyone knows|it is well known|obviously) ", "unsupported_claim"),
    (r"(?:according to|based on) (?:my (?:knowledge|training|data))", "training_data_reference"),
    (r"(?:I (?:think|believe|guess))", "uncertainty"),
    (r"(?:studies show|research indicates) (?:that )?(?:\d+%)", "fabricated_statistic"),
]


def check_confidence(response):
    """Check for hallucination patterns."""
    issues = []
    
    for pattern, issue_type in HALLUCINATION_PATTERNS:
        matches = re.findall(pattern, response, re.IGNORECASE)
        if matches:
            issues.append({
                "type": issue_type,
                "count": len(matches),
            })
    
    # Count certainty markers
    certainty = len(re.findall(r"\b(?:definitely|certainly|absolutely|100%)\b", response, re.IGNORECASE))
    uncertainty = len(re.findall(r"\b(?:maybe|perhaps|possibly|I think|I believe)\b", response, re.IGNORECASE))
    
    return {
        "issues": issues,
        "certainty_markers": certainty,
        "uncertainty_markers": uncertainty,
        "confidence_ratio": round(certainty / max(certainty + uncertainty, 1), 2),
        "recommendation": "review for hallucination" if issues else "no hallucination patterns",
    }


# ============================================================================
# FULL SAFETY WRAPPER
# ============================================================================

def wrap_llm_call(prompt, response=None):
    """Run all safety checks on prompt + response."""
    result = {
        "input_check": check_input(prompt),
        "output_check": check_output(response) if response else None,
        "confidence_check": check_confidence(response) if response else None,
    }
    
    # Overall decision
    input_action = result["input_check"]["action"]
    output_action = result["output_check"]["action"] if result["output_check"] else "ALLOW"
    
    if input_action == "BLOCK" or output_action == "BLOCK":
        result["overall"] = "BLOCK"
        result["reason"] = f"input={input_action}, output={output_action}"
    elif input_action == "WARN" or output_action == "WARN":
        result["overall"] = "WARN"
        result["reason"] = f"input={input_action}, output={output_action}"
    else:
        result["overall"] = "ALLOW"
        result["reason"] = "all checks passed"
    
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["check-input", "check-output", "wrap", "confidence", "stats"])
    parser.add_argument("--prompt", help="input prompt")
    parser.add_argument("--response", help="LLM response")
    args = parser.parse_args()
    
    if args.command == "check-input":
        if not args.prompt:
            print("--prompt required")
            sys.exit(2)
        result = check_input(args.prompt)
        print(json.dumps(result, indent=2))
    
    elif args.command == "check-output":
        if not args.response:
            print("--response required")
            sys.exit(2)
        result = check_output(args.response)
        print(json.dumps(result, indent=2))
    
    elif args.command == "confidence":
        if not args.response:
            print("--response required")
            sys.exit(2)
        result = check_confidence(args.response)
        print(json.dumps(result, indent=2))
    
    elif args.command == "wrap":
        if not args.prompt:
            print("--prompt required")
            sys.exit(2)
        result = wrap_llm_call(args.prompt, args.response)
        print(json.dumps(result, indent=2))
    
    elif args.command == "stats":
        if os.path.exists(SAFETY_LOG):
            log = json.loads(Path(SAFETY_LOG).read_text())
            print(f"Safety log: {len(log)} entries")
            
            from collections import Counter
            actions = Counter(e["action"] for e in log)
            print(f"Actions: {dict(actions)}")
            
            layers = Counter(e["layer"] for e in log)
            print(f"Layers: {dict(layers)}")
            
            # Last 5
            print("\nLast 5 entries:")
            for entry in log[-5:]:
                print(f"  [{entry['timestamp']}] {entry['layer']}: {entry['action']} — {entry['reason']}")
        else:
            print("No safety log")


if __name__ == "__main__":
    main()
