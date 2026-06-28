#!/usr/bin/env python3
"""
v945_zerotrust.py — ZERO-TRUST ARCHITECTURE v9.45
====================================================
Never trust, always verify. Every request authenticated + authorized.

Principles:
1. Verify explicitly — every request must prove identity
2. Least privilege — each component has minimal access
3. Assume breach — log everything, segment network

Components:
- Identity provider (OAuth2 from v9.42)
- Policy engine (per-command authorization)
- Audit logger (blockchain from v9.43)
- Network segmentation (mTLS from v9.42)

Usage:
    python3 v945_zerotrust.py request --identity alice --action "run_gate" --resource "g0_check"
    python3 v945_zerotrust.py policy-list
    python3 v945_zerotrust.py policy-add --subject alice --action "*" --resource "*" --decision allow
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

POLICY_FILE = "/home/z/my-project/scripts/v945_zerotrust_policies.json"
AUDIT_LOG = "/home/z/my-project/audit_trail/v945_zerotrust_audit.jsonl"


# ============================================================================
# POLICY ENGINE
# ============================================================================

def load_policies():
    """Load access control policies."""
    if not os.path.exists(POLICY_FILE):
        # Default policies
        default = {
            "policies": [
                {"id": "p1", "subject": "alice", "action": "*", "resource": "*", "decision": "allow"},
                {"id": "p2", "subject": "bob", "action": "chat", "resource": "*", "decision": "allow"},
                {"id": "p3", "subject": "bob", "action": "run_gate", "resource": "g0_check", "decision": "allow"},
                {"id": "p4", "subject": "bob", "action": "run_gate", "resource": "*", "decision": "deny"},
                {"id": "p5", "subject": "*", "action": "status", "resource": "*", "decision": "allow"},
                {"id": "p6", "subject": "*", "action": "*", "resource": "admin", "decision": "deny"},
            ]
        }
        Path(POLICY_FILE).write_text(json.dumps(default, indent=2))
        return default
    return json.loads(Path(POLICY_FILE).read_text())


def save_policies(policies):
    Path(POLICY_FILE).write_text(json.dumps(policies, indent=2))


def evaluate_policy(subject, action, resource):
    """Evaluate access request against policies. Returns decision + matched policy."""
    policies = load_policies()["policies"]
    
    # Check policies in order (first match wins)
    for p in policies:
        subject_match = p["subject"] == subject or p["subject"] == "*"
        action_match = p["action"] == action or p["action"] == "*"
        resource_match = p["resource"] == resource or p["resource"] == "*"
        
        if subject_match and action_match and resource_match:
            return {
                "decision": p["decision"],
                "matched_policy": p["id"],
                "subject": subject,
                "action": action,
                "resource": resource,
            }
    
    # Default deny
    return {
        "decision": "deny",
        "matched_policy": "default-deny",
        "subject": subject,
        "action": action,
        "resource": resource,
    }


def authorize_request(identity, action, resource):
    """Full zero-trust authorization: verify identity + check policy + audit."""
    
    # Step 1: Verify identity (simulated — in real ZT, check OAuth2 token)
    # Here we just check if identity is non-empty
    if not identity:
        return {
            "authorized": False,
            "reason": "no identity provided",
            "audit_logged": False,
        }
    
    # Step 2: Evaluate policy
    decision = evaluate_policy(identity, action, resource)
    
    # Step 3: Audit log (always, regardless of decision)
    audit_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "identity": identity,
        "action": action,
        "resource": resource,
        "decision": decision["decision"],
        "policy": decision["matched_policy"],
        "request_hash": hashlib.sha256(f"{identity}|{action}|{resource}|{time.time()}".encode()).hexdigest()[:16],
    }
    
    Path(AUDIT_LOG).parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(audit_entry) + "\n")
    
    return {
        "authorized": decision["decision"] == "allow",
        "decision": decision,
        "audit_logged": True,
        "audit_hash": audit_entry["request_hash"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["request", "policy-list", "policy-add", "policy-remove", "audit-show"])
    parser.add_argument("--identity", help="requesting identity")
    parser.add_argument("--action", help="requested action")
    parser.add_argument("--resource", help="requested resource")
    parser.add_argument("--subject", help="policy subject")
    parser.add_argument("--decision", choices=["allow", "deny"], default="allow")
    parser.add_argument("--id", help="policy ID for remove")
    args = parser.parse_args()
    
    if args.command == "request":
        if not args.identity or not args.action or not args.resource:
            print("--identity, --action, --resource required")
            sys.exit(2)
        result = authorize_request(args.identity, args.action, args.resource)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["authorized"] else 1)
    
    elif args.command == "policy-list":
        policies = load_policies()
        print(json.dumps(policies, indent=2))
    
    elif args.command == "policy-add":
        if not args.subject or not args.action or not args.resource:
            print("--subject, --action, --resource required")
            sys.exit(2)
        policies = load_policies()
        new_id = f"p{len(policies['policies']) + 1}"
        policies["policies"].append({
            "id": new_id,
            "subject": args.subject,
            "action": args.action,
            "resource": args.resource,
            "decision": args.decision,
        })
        save_policies(policies)
        print(f"Policy {new_id} added")
    
    elif args.command == "policy-remove":
        if not args.id:
            print("--id required")
            sys.exit(2)
        policies = load_policies()
        policies["policies"] = [p for p in policies["policies"] if p["id"] != args.id]
        save_policies(policies)
        print(f"Policy {args.id} removed")
    
    elif args.command == "audit-show":
        if os.path.exists(AUDIT_LOG):
            lines = Path(AUDIT_LOG).read_text().strip().split("\n")
            print(f"Audit entries: {len(lines)}")
            for line in lines[-10:]:  # last 10
                entry = json.loads(line)
                emoji = "✅" if entry["decision"] == "allow" else "❌"
                print(f"  {emoji} [{entry['timestamp']}] {entry['identity']} → {entry['action']}/{entry['resource']} = {entry['decision']}")
        else:
            print("No audit entries")


if __name__ == "__main__":
    main()
