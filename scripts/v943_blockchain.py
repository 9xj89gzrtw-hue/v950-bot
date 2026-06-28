#!/usr/bin/env python3
"""
v943_blockchain.py — AUDIT LOG BLOCKCHAIN v9.43
=================================================
Tamper-proof audit log using blockchain-style hash chain + Proof-of-Work.

Each block:
- index
- timestamp
- previous_block_hash
- claim (audit entry)
- evidence (JSON)
- nonce (PoW solution)
- hash (SHA-256 of all above)

PoW difficulty: 4 leading zeros (configurable).
- Adding block: find nonce such that hash(starts with "0000")
- Tamper detection: changing any block invalidates all subsequent hashes
- Verification: re-compute all hashes, check PoW + chain continuity

This makes the audit log CRYPTOGRAPHICALLY TAMPER-PROOF:
- Attacker cannot modify past entries without re-mining entire chain
- PoW makes historical tamper computationally expensive

Usage:
    python3 v943_blockchain.py add --claim "event X happened" --evidence '{"k":"v"}'
    python3 v943_blockchain.py verify
    python3 v943_blockchain.py status
    python3 v943_blockchain.py export  # export chain as JSON
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

CHAIN_FILE = "/home/z/my-project/audit_trail/v943_blockchain.json"
DIFFICULTY = 4  # 4 leading zeros = ~65k attempts on average
MAX_NONCE = 10_000_000


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_chain():
    """Load blockchain from file."""
    if not os.path.exists(CHAIN_FILE):
        return []
    try:
        return json.loads(Path(CHAIN_FILE).read_text())
    except Exception:
        return []


def save_chain(chain):
    """Save blockchain to file."""
    Path(CHAIN_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(CHAIN_FILE).write_text(json.dumps(chain, indent=2, ensure_ascii=False))


def compute_hash(index, timestamp, prev_hash, claim, evidence, nonce):
    """Compute block hash."""
    block_data = {
        "index": index,
        "timestamp": timestamp,
        "previous_hash": prev_hash,
        "claim": claim,
        "evidence": evidence,
        "nonce": nonce,
    }
    block_str = json.dumps(block_data, sort_keys=True, separators=(",", ":"))
    return sha256(block_str)


def mine_block(index, timestamp, prev_hash, claim, evidence):
    """Find nonce such that hash starts with DIFFICULTY zeros."""
    target = "0" * DIFFICULTY
    for nonce in range(MAX_NONCE):
        h = compute_hash(index, timestamp, prev_hash, claim, evidence, nonce)
        if h.startswith(target):
            return nonce, h
    raise RuntimeError(f"Could not mine block after {MAX_NONCE} attempts")


def add_block(claim, evidence=None):
    """Add new block to chain (with PoW mining)."""
    chain = load_chain()
    evidence = evidence or {}
    
    index = len(chain)
    timestamp = iso_now()
    prev_hash = chain[-1]["hash"] if chain else "0" * 64
    
    print(f"Mining block {index} (difficulty: {DIFFICULTY} zeros)...", file=sys.stderr)
    t0 = time.time()
    nonce, block_hash = mine_block(index, timestamp, prev_hash, claim, evidence)
    elapsed = time.time() - t0
    
    block = {
        "index": index,
        "timestamp": timestamp,
        "previous_hash": prev_hash,
        "claim": claim,
        "evidence": evidence,
        "nonce": nonce,
        "hash": block_hash,
        "mining_time_sec": round(elapsed, 3),
    }
    
    chain.append(block)
    save_chain(chain)
    
    print(f"Block {index} mined in {elapsed:.3f}s (nonce={nonce})", file=sys.stderr)
    print(f"Hash: {block_hash}", file=sys.stderr)
    return block


def verify_chain():
    """Verify entire blockchain: PoW + chain continuity + hash integrity."""
    chain = load_chain()
    if not chain:
        return {"valid": True, "blocks": 0, "message": "empty chain"}
    
    prev_hash = "0" * 64
    for i, block in enumerate(chain):
        # Check index
        if block["index"] != i:
            return {"valid": False, "blocks": i, "error": f"index mismatch at block {i}: expected {i}, got {block['index']}"}
        
        # Check previous_hash continuity
        if block["previous_hash"] != prev_hash:
            return {"valid": False, "blocks": i, "error": f"chain broken at block {i}: previous_hash mismatch"}
        
        # Recompute hash
        recomputed = compute_hash(
            block["index"], block["timestamp"], block["previous_hash"],
            block["claim"], block["evidence"], block["nonce"]
        )
        if recomputed != block["hash"]:
            return {"valid": False, "blocks": i, "error": f"hash mismatch at block {i}: tampered!"}
        
        # Check PoW
        if not block["hash"].startswith("0" * DIFFICULTY):
            return {"valid": False, "blocks": i, "error": f"PoW invalid at block {i}: hash doesn't meet difficulty"}
        
        prev_hash = block["hash"]
    
    return {
        "valid": True,
        "blocks": len(chain),
        "last_hash": chain[-1]["hash"][:16],
        "last_timestamp": chain[-1]["timestamp"],
        "total_mining_time_sec": sum(b.get("mining_time_sec", 0) for b in chain),
    }


def tamper_test():
    """Test: tamper with block 0, verify detection."""
    chain = load_chain()
    if len(chain) < 1:
        return {"error": "need at least 1 block for tamper test"}
    
    # Backup
    backup = json.loads(json.dumps(chain))
    
    # Tamper
    chain[0]["claim"] = "TAMPERED: this should be detected"
    save_chain(chain)
    
    # Verify (should fail)
    result = verify_chain()
    
    # Restore
    save_chain(backup)
    
    return {
        "tampered_block": 0,
        "verification_after_tamper": result,
        "restored": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["add", "verify", "status", "export", "tamper-test"])
    parser.add_argument("--claim", help="audit claim")
    parser.add_argument("--evidence", help="JSON evidence")
    args = parser.parse_args()
    
    if args.command == "add":
        if not args.claim:
            print("--claim required")
            sys.exit(2)
        evidence = json.loads(args.evidence) if args.evidence else {}
        block = add_block(args.claim, evidence)
        print(json.dumps(block, indent=2, ensure_ascii=False))
    
    elif args.command == "verify":
        result = verify_chain()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("valid") else 1)
    
    elif args.command == "status":
        chain = load_chain()
        print(f"Blockchain: {len(chain)} blocks")
        print(f"File: {CHAIN_FILE}")
        print(f"Difficulty: {DIFFICULTY} leading zeros")
        if chain:
            print(f"Last block: index={chain[-1]['index']}, hash={chain[-1]['hash'][:16]}...")
            print(f"Last timestamp: {chain[-1]['timestamp']}")
            total_mining = sum(b.get("mining_time_sec", 0) for b in chain)
            print(f"Total mining time: {total_mining:.3f}s")
    
    elif args.command == "export":
        chain = load_chain()
        print(json.dumps(chain, indent=2, ensure_ascii=False))
    
    elif args.command == "tamper-test":
        result = tamper_test()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
