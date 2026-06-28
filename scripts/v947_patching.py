#!/usr/bin/env python3
"""
v947_patching.py — AUTOMATED PATCHING v9.47
=============================================
Automatically patches safety filters when red team finds vulnerabilities.

Workflow:
1. Run red team attacks
2. For each vulnerability, generate patch (new regex pattern)
3. Apply patch to v945_safety.py
4. Re-run red team to verify fix
5. Log patch to audit trail

Usage:
    python3 v947_patching.py scan      # scan for vulnerabilities + auto-patch
    python3 v947_patching.py history   # show patch history
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/z/my-project/scripts")

SAFETY_FILE = "/home/z/my-project/scripts/v945_safety.py"
REDTEAM_FILE = "/home/z/my-project/scripts/v946_redteam.py"
PATCH_LOG = "/home/z/my-project/audit_trail/v947_patches.jsonl"


# ============================================================================
# PATCH GENERATOR
# ============================================================================

def generate_patch(attack):
    """Generate regex pattern for an attack that wasn't caught."""
    payload = attack["payload"]
    category = attack["category"]
    name = attack["name"]
    
    patterns = []
    
    # Generate patterns based on category
    if category == "prompt_injection":
        # Extract key phrases
        if "ignore" in payload.lower():
            patterns.append((r"ignore\s+(?:all\s+)?(?:previous|prior)", "ignore-variant"))
        if "pretend" in payload.lower() or "act as" in payload.lower():
            patterns.append((r"(?:pretend|act\s+as)\s+(?:that\s+you|you\s+are)", "pretend-variant"))
        if "system prompt" in payload.lower():
            patterns.append(r"system\s+prompt", "system-prompt-extraction")
    
    elif category == "jailbreak":
        if "developer mode" in payload.lower():
            patterns.append((r"developer\s+mode.*(?:output|enable|allow)", "developer-mode-variant"))
        if "hypothetical" in payload.lower():
            patterns.append((r"in\s+a\s+(?:purely\s+)?hypothetical", "hypothetical-variant"))
        if "translate" in payload.lower():
            patterns.append((r"translate\s+.*(?:then|and)\s+(?:explain|tell)", "translate-variant"))
    
    elif category == "toxicity":
        if any(w in payload.lower() for w in ["hurt", "kill", "harm"]):
            patterns.append((r"how\s+(?:do|to|can)\s+i?\s*(?:hurt|kill|harm)", "harm-request"))
        if any(w in payload.lower() for w in ["bomb", "weapon", "explosive"]):
            patterns.append((r"(?:make|create|build)\s+(?:a\s+)?(?:bomb|weapon|explosive)", "weapon-request"))
        if any(w in payload.lower() for w in ["meth", "drug", "cocaine"]):
            patterns.append((r"(?:recipe|make|create|synthesize)\s+(?:meth|drug|cocaine)", "drug-request"))
    
    elif category == "pii_extraction":
        if "system prompt" in payload.lower() or "instructions" in payload.lower():
            patterns.append((r"(?:what\s+is|show|reveal|tell)\s+.*(?:system\s+)?(?:prompt|instructions?)", "prompt-extraction"))
        if "describe" in payload.lower():
            patterns.append((r"describe\s+.*(?:instructions|prompt|rules)", "indirect-extraction"))
    
    elif category == "hallucination":
        if "cite" in payload.lower():
            patterns.append((r"cite\s+\d+\s+papers?", "citation-request"))
        if "percentage" in payload.lower():
            patterns.append((r"what\s+percentage\s+of", "statistics-request"))
    
    elif category == "resource_exhaustion":
        patterns.append((None, "length-check"))  # handled by MAX_PROMPT_LENGTH
    
    return patterns


def apply_patch(pattern, name, category, severity=0.85):
    """Apply a single regex patch to safety.py."""
    if pattern is None:
        return {"applied": False, "reason": "no pattern needed (length check)"}
    
    # Check if pattern already exists
    content = Path(SAFETY_FILE).read_text()
    if pattern in content:
        return {"applied": False, "reason": "pattern already exists"}
    
    # Add to TOXICITY_PATTERNS (where most attacks are caught)
    new_entry = f'    (r"{pattern}", "{name}", {severity}),\n'
    
    # Find the end of TOXICITY_PATTERNS list
    match = re.search(r'(TOXICITY_PATTERNS\s*=\s*\[.*?\n\])', content, re.S)
    if match:
        insert_pos = match.end() - 2  # before closing ]
        patched = content[:insert_pos] + new_entry + content[insert_pos:]
        Path(SAFETY_FILE).write_text(patched)
        return {"applied": True, "pattern": pattern, "name": name}
    
    return {"applied": False, "reason": "could not find TOXICITY_PATTERNS"}


def log_patch(patch_info):
    """Log patch to audit trail."""
    Path(PATCH_LOG).parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **patch_info,
    }
    with open(PATCH_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ============================================================================
# AUTOMATED SCAN + PATCH
# ============================================================================

def scan_and_patch():
    """Run red team, find vulnerabilities, auto-patch."""
    print("=== Automated Vulnerability Scan + Patch ===\n")
    
    # Step 1: Run red team
    print("[1/4] Running red team...")
    result = subprocess.run(
        ["python3", REDTEAM_FILE, "run"],
        capture_output=True, text=True, timeout=120
    )
    
    # Parse report
    report_file = Path("/home/z/my-project/scripts/v946_redteam_report.json")
    if not report_file.exists():
        print("❌ Red team report not found")
        return
    
    report = json.loads(report_file.read_text())
    vulns = report.get("vulnerabilities", [])
    
    print(f"   Found {len(vulns)} vulnerabilities")
    
    if not vulns:
        print("\n✅ No vulnerabilities found! All attacks blocked.")
        return
    
    # Step 2: Generate patches
    print(f"\n[2/4] Generating patches for {len(vulns)} vulnerabilities...")
    
    # Load attack definitions
    from v946_redteam import ATTACKS
    patches_applied = 0
    patches_skipped = 0
    
    for vuln in vulns:
        attack = next((a for a in ATTACKS if a["id"] == vuln["id"]), None)
        if not attack:
            continue
        
        patterns = generate_patch(attack)
        for pattern, name in patterns:
            result = apply_patch(pattern, name, vuln["category"])
            if result["applied"]:
                print(f"   ✅ Patched: {vuln['id']} ({name})")
                log_patch({
                    "attack_id": vuln["id"],
                    "category": vuln["category"],
                    "pattern": pattern,
                    "name": name,
                    "status": "applied",
                })
                patches_applied += 1
            else:
                print(f"   ⏭️ Skipped: {vuln['id']} ({result['reason']})")
                patches_skipped += 1
    
    print(f"\n   Patches applied: {patches_applied}")
    print(f"   Patches skipped: {patches_skipped}")
    
    # Step 3: Re-run red team to verify
    if patches_applied > 0:
        print(f"\n[3/4] Re-running red team to verify patches...")
        result = subprocess.run(
            ["python3", REDTEAM_FILE, "run"],
            capture_output=True, text=True, timeout=120
        )
        
        # Parse new report
        new_report = json.loads(report_file.read_text())
        new_vulns = new_report.get("vulnerabilities", [])
        new_block_rate = new_report.get("block_rate_pct", 0)
        
        print(f"   Block rate: {report['block_rate_pct']}% → {new_block_rate}%")
        print(f"   Vulnerabilities: {len(vulns)} → {len(new_vulns)}")
        
        if len(new_vulns) < len(vulns):
            print(f"\n✅ Patches effective! Reduced vulnerabilities by {len(vulns) - len(new_vulns)}")
        elif len(new_vulns) == 0:
            print(f"\n✅ All vulnerabilities patched!")
        else:
            print(f"\n⚠️ {len(new_vulns)} vulnerabilities remain — need manual review")
    else:
        print(f"\n[3/4] No patches applied — skipping verification")
    
    # Step 4: Summary
    print(f"\n[4/4] Summary")
    print(f"   Initial vulnerabilities: {len(vulns)}")
    print(f"   Patches applied: {patches_applied}")
    print(f"   Remaining vulnerabilities: {len(new_vulns) if patches_applied > 0 else len(vulns)}")
    print(f"   Patch log: {PATCH_LOG}")


def show_history():
    """Show patch history."""
    if not os.path.exists(PATCH_LOG):
        print("No patches applied yet")
        return
    
    lines = Path(PATCH_LOG).read_text().strip().split("\n")
    print(f"Patch History ({len(lines)} patches):\n")
    for line in lines:
        entry = json.loads(line)
        print(f"  [{entry['timestamp']}] {entry['attack_id']}: {entry['name']} → {entry['status']}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["scan", "history"])
    args = parser.parse_args()
    
    if args.command == "scan":
        scan_and_patch()
    elif args.command == "history":
        show_history()


if __name__ == "__main__":
    main()
