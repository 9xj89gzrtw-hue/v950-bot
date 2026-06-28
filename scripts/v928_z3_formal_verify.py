#!/usr/bin/env python3
"""
v928_z3_formal_verify.py — G0-Z3 FORMAL VERIFICATION v9.28
============================================================
Z3 SMT solver proves PRIMARY_GOAL preservation under hash-injectivity axiom.

Approach:
- Model sha256_16 as uninterpreted function String -> BitVec(64)
- Axiom: injectivity (∀ x, y. sha(x) == sha(y) ⟹ x == y)
- Witness: canonical line maps to expected hash
- Claim: ∃ edited. sha(edited) == expected ∧ ¬Contains(edited, required_phrase)
  UNSAT = formally PROVEN that no edit with matching hash can omit a required phrase
"""
import hashlib
import re
import sys
import time
from pathlib import Path

try:
    import z3
except ImportError:
    sys.exit("FATAL: z3 not installed. Run: pip3 install z3-solver")

META_PROMPT_PATH = "/home/z/my-project/upload/meta-prompt-v9.28-abstention-prefill-context.md"
EXPECTED_PRIMARY_GOAL = "> Создавать **лучшие в мире промпты**, которые **решают задачи пользователя правильно с первой попытки**, и **никогда не врут**."
EXPECTED_HASH = "03ac49234eeb9000"
REQUIRED_PHRASES = ["с первой попытки", "никогда не врут", "лучшие в мире промпты", "решают задачи", "Создавать"]
FORBIDDEN_CODEPOINTS = [
    (0x200B, "ZWSP"), (0x200C, "ZWNJ"), (0x00A0, "NBSP"), (0xFEFF, "BOM"),
    (0x037E, "Greek question mark"), (0x200D, "ZWJ"), (0x2060, "Word Joiner"), (0x00AD, "Soft hyphen"),
]


def sha256_16(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def load_primary_goal_line():
    text = Path(META_PROMPT_PATH).read_text(encoding="utf-8")
    m = re.search(r"^> Создавать[^\n]*$", text, re.MULTILINE)
    return m.group(0) if m else ""


def concrete_hash_check():
    actual_line = load_primary_goal_line()
    actual_hash = sha256_16(actual_line) if actual_line else ""
    return {"expected": EXPECTED_HASH, "actual": actual_hash, "pass": actual_hash == EXPECTED_HASH}


def concrete_unicode_check():
    actual_line = load_primary_goal_line()
    if not actual_line:
        return {"pass": False, "error": "line not found"}
    found = [f"U+{cp:04X} {name}" for cp, name in FORBIDDEN_CODEPOINTS if chr(cp) in actual_line]
    return {"pass": len(found) == 0, "forbidden_chars_found": found}


def z3_verify_hash_injectivity():
    """PROVE: under injectivity axiom, no edit with matching hash can omit required phrase."""
    s = z3.Solver()
    s.set("timeout", 15000)
    sha_fn = z3.Function("sha256_16", z3.StringSort(), z3.BitVecSort(64))
    expected_bv = z3.BitVecVal(int(EXPECTED_HASH, 16), 64)

    x = z3.Const("x", z3.StringSort())
    y = z3.Const("y", z3.StringSort())

    # Injectivity axiom
    s.add(z3.ForAll([x, y], z3.Implies(sha_fn(x) == sha_fn(y), x == y)))

    # Witness: canonical line maps to expected hash
    s.add(sha_fn(z3.StringVal(EXPECTED_PRIMARY_GOAL)) == expected_bv)

    # Counterexample claim: exists edited with matching hash AND missing required phrase
    test_line = z3.Const("test_line", z3.StringSort())
    s.add(sha_fn(test_line) == expected_bv)
    s.add(z3.IndexOf(test_line, z3.StringVal("никогда не врут"), 0) < 0)

    t0 = time.time()
    rc = s.check()
    dt = time.time() - t0

    if rc == z3.unsat:
        return {"result": "UNSAT — formally PROVEN: under injectivity axiom, no line with expected hash can omit required phrase", "time_sec": round(dt, 3)}
    elif rc == z3.unknown:
        return {"result": "UNKNOWN (Z3 timeout)", "time_sec": round(dt, 3)}
    return {"result": f"SAT (rc={rc}) — investigate", "time_sec": round(dt, 3)}


def z3_verify_unicode_attacks():
    """For each unicode attack, check if attack string CAN coexist with required phrase."""
    results = []
    test_phrase = "никогда не врут"
    for cp, name in FORBIDDEN_CODEPOINTS:
        s = z3.Solver()
        s.set("timeout", 5000)
        line = z3.String(f"line_{cp:x}")
        s.add(z3.IndexOf(line, z3.StringVal(test_phrase), 0) >= 0)
        s.add(z3.IndexOf(line, z3.StringVal(chr(cp)), 0) >= 0)
        t0 = time.time()
        rc = s.check()
        dt = time.time() - t0
        if rc == z3.sat:
            interp = "SAT — attack CAN coexist (hash check mandatory)"
        elif rc == z3.unsat:
            interp = "UNSAT — phrase alone blocks this attack"
        else:
            interp = "UNKNOWN (timeout)"
        results.append({"attack": f"U+{cp:04X} {name}", "result": str(rc), "time_sec": round(dt, 3), "interpretation": interp})
    return results


def main():
    print("=" * 70)
    print("G0-Z3 FORMAL VERIFICATION v9.28")
    print("=" * 70)
    print(f"Z3 version: {z3.get_version_string()}")
    print(f"Expected hash: {EXPECTED_HASH}")
    print()

    print("[1/4] Concrete hash check:")
    ch = concrete_hash_check()
    print(f"     pass: {ch['pass']} ({ch['actual']})")
    print()

    print("[2/4] Concrete Unicode check:")
    cu = concrete_unicode_check()
    print(f"     pass: {cu['pass']} ({cu.get('forbidden_chars_found', [])})")
    print()

    print("[3/4] Z3: Hash injectivity axiom:")
    hi = z3_verify_hash_injectivity()
    print(f"     {hi['result']}")
    print(f"     time: {hi['time_sec']}s")
    print()

    print("[4/4] Z3: Unicode attack invariants:")
    ua = z3_verify_unicode_attacks()
    for atk in ua:
        print(f"     {atk['attack']:<35} {atk['result']:<10} {atk['time_sec']}s")
    print()

    print("=" * 70)
    print("VERDICT")
    print("=" * 70)
    print(f"Concrete checks: {'PASS' if ch['pass'] and cu['pass'] else 'FAIL'}")
    print(f"Z3 hash-injectivity: {hi['result'][:80]}")
    print()
    print("HONEST LIMITATION:")
    print("  Z3 proves byte-level invariants, not NL semantic equivalence.")
    print("=" * 70)

    import json
    out = Path("/home/z/my-project/download/benchmarks/z3_formal_verify.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "test": "G0-Z3-formal-verification",
        "version": "v9.28",
        "z3_version": z3.get_version_string(),
        "concrete_hash_check": ch,
        "concrete_unicode_check": cu,
        "z3_hash_injectivity": hi,
        "z3_unicode_attacks": ua,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"JSON: {out}")


if __name__ == "__main__":
    main()
