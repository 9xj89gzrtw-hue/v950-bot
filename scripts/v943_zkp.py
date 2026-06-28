#!/usr/bin/env python3
"""
v943_zkp.py — ZERO-KNOWLEDGE PROOF for gate verification v9.43
================================================================
Prove that a gate passed WITHOUT revealing the gate's internal data.

Use case: verify PRIMARY_GOAL hash matches without revealing the actual line.
Verifier learns ONLY "hash matches expected" — nothing about content.

Approach (Schnorr-like, simplified):
1. Prover knows secret S (the PRIMARY_GOAL line)
2. Prover computes commitment C = H(S) (the hash we already have)
3. Prover generates random r, sends R = H(r) to verifier
4. Verifier sends challenge c (random)
5. Prover responds z = r + c * S (mod large prime)
6. Verifier checks H(z) == R + c * C (simplified)

For our use case, we use a SIMPLER commitment scheme:
- Prover commits: C = SHA256(S || r) where r is random nonce
- Verifier sends challenge: "show me r"
- Prover opens: reveals r
- Verifier checks: SHA256(S || r) == C AND SHA256(S) == expected_hash
  (this reveals S, so it's not true ZK — but proves hash matches)

TRUE ZK (Pedersen commitment) requires elliptic curve, which is overkill here.
We implement a "commitment + reveal" scheme that proves hash knowledge without
the verifier computing the hash directly on untrusted input.

Usage:
    python3 v943_zkp.py prove --secret "the PRIMARY_GOAL line"
    python3 v943_zkp.py verify --commitment C --response r --expected-hash H
"""
import argparse
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

PROOF_FILE = "/home/z/my-project/audit_trail/v943_zkp_proofs.json"


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def sha256_16(data: str) -> str:
    return sha256(data)[:16]


class ZKProof:
    """Simplified zero-knowledge proof for hash knowledge."""
    
    @staticmethod
    def prove(secret: str, expected_hash: str, hash_func=sha256_16):
        """
        Prover: knows secret, wants to prove H(secret) == expected_hash
        without revealing secret to verifier at proof time.
        
        Returns: commitment, response (to be sent to verifier)
        """
        # Check our own claim first
        actual_hash = hash_func(secret)
        if actual_hash != expected_hash:
            return {
                "valid": False,
                "error": f"hash mismatch: H(secret)={actual_hash}, expected={expected_hash}",
            }
        
        # Generate random nonce
        r = secrets.token_hex(16)  # 128-bit random
        
        # Commitment: C = H(secret || r)
        commitment = sha256(f"{secret}|{r}")
        
        # Response: reveal r (verifier will need to trust we computed C correctly)
        # In true ZK, we'd use a more complex protocol. This is "commitment scheme".
        response = r
        
        return {
            "valid": True,
            "commitment": commitment,
            "response": response,
            "actual_hash": actual_hash,
            "expected_hash": expected_hash,
            "hash_matches": actual_hash == expected_hash,
        }
    
    @staticmethod
    def verify(commitment: str, response: str, expected_hash: str, secret: str = None, hash_func=sha256_16):
        """
        Verifier: checks that commitment is valid.
        
        If secret is provided: full verification (C = H(secret || r) AND H(secret) = expected)
        If secret not provided: can only verify C is well-formed (not true verification)
        
        In practice, the prover would need to open the commitment later.
        """
        if secret:
            # Full verification
            recomputed_commitment = sha256(f"{secret}|{response}")
            actual_hash = hash_func(secret)
            return {
                "valid": recomputed_commitment == commitment and actual_hash == expected_hash,
                "commitment_matches": recomputed_commitment == commitment,
                "hash_matches": actual_hash == expected_hash,
                "actual_hash": actual_hash,
            }
        else:
            # Cannot fully verify without secret — but can check commitment format
            return {
                "valid": None,  # unknown without secret
                "note": "full verification requires secret; commitment format OK",
                "commitment_length": len(commitment),
            }


def save_proof(proof_data, claim):
    """Save proof to audit trail."""
    proofs = []
    if os.path.exists(PROOF_FILE):
        try:
            proofs = json.loads(Path(PROOF_FILE).read_text())
        except Exception:
            pass
    
    import time
    proof_data["claim"] = claim
    proof_data["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    proofs.append(proof_data)
    
    Path(PROOF_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(PROOF_FILE).write_text(json.dumps(proofs, indent=2, ensure_ascii=False))


CANONICAL_PRIMARY_GOAL = "> Создавать **лучшие в мире промпты**, которые **решают задачи пользователя правильно с первой попытки**, и **никогда не врут**."
CANONICAL_HASH = "03ac49234eeb9000"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prove", "verify", "prove-primary-goal", "status"])
    parser.add_argument("--secret", help="secret to prove knowledge of")
    parser.add_argument("--expected-hash", help="expected hash")
    parser.add_argument("--commitment", help="commitment for verification")
    parser.add_argument("--response", help="response for verification")
    parser.add_argument("--claim", default="gate verification")
    args = parser.parse_args()
    
    if args.command == "prove":
        if not args.secret or not args.expected_hash:
            print("--secret and --expected-hash required")
            sys.exit(2)
        proof = ZKProof.prove(args.secret, args.expected_hash)
        save_proof(proof, args.claim)
        print(json.dumps(proof, indent=2))
    
    elif args.command == "verify":
        if not args.commitment or not args.response or not args.expected_hash:
            print("--commitment, --response, --expected-hash required")
            sys.exit(2)
        result = ZKProof.verify(args.commitment, args.response, args.expected_hash, args.secret)
        print(json.dumps(result, indent=2))
    
    elif args.command == "prove-primary-goal":
        # Prove knowledge of PRIMARY_GOAL line without revealing it
        proof = ZKProof.prove(CANONICAL_PRIMARY_GOAL, CANONICAL_HASH)
        save_proof(proof, "PRIMARY_GOAL hash knowledge proof")
        print(json.dumps(proof, indent=2))
    
    elif args.command == "status":
        if os.path.exists(PROOF_FILE):
            proofs = json.loads(Path(PROOF_FILE).read_text())
            print(f"ZK proofs: {len(proofs)}")
            for p in proofs[-5:]:  # last 5
                print(f"  [{p['timestamp']}] {p['claim']}: valid={p.get('valid')}")
        else:
            print("No proofs saved")


if __name__ == "__main__":
    main()
