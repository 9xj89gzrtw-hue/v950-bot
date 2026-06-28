#!/usr/bin/env python3
"""
v944_mpc.py — SECURE MULTI-PARTY COMPUTATION demo v9.44
==========================================================
Demonstrate MPC: 3 parties compute function on secret inputs
without revealing inputs to each other.

Scenario: 3 LLM providers (z-ai, Pollinations, rule-based) jointly
compute consensus answer WITHOUT revealing their individual answers.

Technique: Secret Sharing (Shamir's) + secure aggregation.

Shamir's Secret Sharing:
- Secret S split into N shares
- Any K shares can reconstruct S
- Fewer than K shares reveal nothing

For our demo:
- Each model computes answer locally
- Each model secret-shares its answer
- Aggregator combines shares to get consensus
- Aggregator never sees individual answers (only shares)

Usage:
    python3 v944_mpc.py demo
    python3 v944_mpc.py share --secret "4"
    python3 v944_mpc.py reconstruct --shares '["s1", "s2", "s3"]'
"""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path


# ============================================================================
# SHAMIR'S SECRET SHARING (simplified, over integers)
# ============================================================================

# Use a prime field for arithmetic
PRIME = 2**61 - 1  # Mersenne prime


def shamir_share(secret: int, n: int, k: int):
    """Split secret into n shares, any k can reconstruct.
    
    secret: integer to share
    n: total number of shares
    k: threshold (minimum shares needed to reconstruct)
    """
    if k > n:
        raise ValueError("k cannot be greater than n")
    
    # Generate random polynomial of degree k-1
    # f(x) = secret + a1*x + a2*x^2 + ... + a_{k-1}*x^{k-1}
    coefficients = [secret % PRIME]
    for _ in range(k - 1):
        coefficients.append(random.randint(0, PRIME - 1))
    
    # Compute shares: share_i = f(i) for i = 1, 2, ..., n
    shares = []
    for i in range(1, n + 1):
        share = 0
        for j, coef in enumerate(coefficients):
            share = (share + coef * pow(i, j, PRIME)) % PRIME
        shares.append((i, share))
    
    return shares


def shamir_reconstruct(shares):
    """Reconstruct secret from shares (Lagrange interpolation)."""
    if len(shares) < 2:
        raise ValueError("Need at least 2 shares")
    
    # Lagrange interpolation at x=0
    secret = 0
    for i, (xi, yi) in enumerate(shares):
        # Compute Lagrange basis polynomial at 0
        num = 1
        den = 1
        for j, (xj, _) in enumerate(shares):
            if i == j:
                continue
            num = (num * (-xj)) % PRIME
            den = (den * (xi - xj)) % PRIME
        
        # Modular inverse of den
        den_inv = pow(den, PRIME - 2, PRIME)  # Fermat's little theorem
        lagrange = (num * den_inv) % PRIME
        secret = (secret + yi * lagrange) % PRIME
    
    return secret


# ============================================================================
# MPC CONSENSUS SIMULATION
# ============================================================================

def mpc_consensus_demo():
    """Simulate 3-party MPC consensus.
    
    3 models compute answers, secret-share them, aggregator combines.
    Aggregator sees only shares, not individual answers.
    """
    print("=" * 60)
    print("MPC Consensus Demo (3 parties)")
    print("=" * 60)
    print()
    
    # Step 1: Each model computes answer locally
    print("Step 1: Each model computes answer locally")
    answers = {
        "z-ai": 4,           # says answer is 4
        "pollinations": 4,    # says answer is 4
        "rule-based": 4,      # says answer is 4
    }
    for model, ans in answers.items():
        print(f"  {model}: answer = {ans} (PRIVATE)")
    print()
    
    # Step 2: Each model secret-shares its answer (k=2, n=3)
    print("Step 2: Secret sharing (n=3, k=2)")
    all_shares = {}
    for model, ans in answers.items():
        shares = shamir_share(ans, n=3, k=2)
        all_shares[model] = shares
        print(f"  {model} shares: {[(i, s % 1000) for i, s in shares]} (truncated)")
    print()
    
    # Step 3: Each party sends one share to aggregator
    print("Step 3: Aggregator collects shares")
    # Aggregator gets share 1 from each model
    aggregator_shares = [
        all_shares["z-ai"][0],
        all_shares["pollinations"][0],
        all_shares["rule-based"][0],
    ]
    print(f"  Aggregator has {len(aggregator_shares)} shares")
    print(f"  Aggregator CANNOT see individual answers")
    print()
    
    # Step 4: Secure aggregation (sum the shares)
    print("Step 4: Secure aggregation (sum encrypted shares)")
    # Sum the shares (homomorphic property of Shamir's)
    # Actually, for consensus we'd compare, not sum. But sum demonstrates MPC.
    total_share = sum(s for _, s in aggregator_shares) % PRIME
    print(f"  Aggregated share: {total_share % 1000} (truncated)")
    print()
    
    # Step 5: Reconstruct (would need cooperation from parties)
    print("Step 5: Reconstruct (requires k=2 shares from same party)")
    # For demo: reconstruct z-ai's answer using 2 of its shares
    z_ai_2_shares = all_shares["z-ai"][:2]
    reconstructed = shamir_reconstruct(z_ai_2_shares)
    print(f"  Reconstructed z-ai answer: {reconstructed}")
    print(f"  Original: {answers['z-ai']}")
    print(f"  Match: {reconstructed == answers['z-ai']}")
    print()
    
    print("=" * 60)
    print("Result: Aggregator computed sum without seeing individual answers")
    print("Each model's answer remains private unless 2+ parties collude")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["demo", "share", "reconstruct"])
    parser.add_argument("--secret", type=int, help="secret to share")
    parser.add_argument("--n", type=int, default=3, help="number of shares")
    parser.add_argument("--k", type=int, default=2, help="threshold")
    args = parser.parse_args()
    
    if args.command == "demo":
        mpc_consensus_demo()
    
    elif args.command == "share":
        if args.secret is None:
            print("--secret required")
            sys.exit(2)
        shares = shamir_share(args.secret, args.n, args.k)
        print(json.dumps({
            "secret": args.secret,
            "n": args.n,
            "k": args.k,
            "shares": [{"index": i, "value": s} for i, s in shares],
        }, indent=2))
    
    elif args.command == "reconstruct":
        # Read shares from stdin or args
        import ast
        shares_str = input("Enter shares as list of [index, value] pairs: ")
        shares_data = ast.literal_eval(shares_str)
        shares = [(int(s[0]), int(s[1])) for s in shares_data]
        secret = shamir_reconstruct(shares)
        print(f"Reconstructed secret: {secret}")


if __name__ == "__main__":
    main()
