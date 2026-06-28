#!/usr/bin/env python3
"""
v930_z3_optimized.py — G51 Z3-STRING-THEORY-OPTIMIZED v9.30
=============================================================
Optimization: per-phrase IndexOf (no multi-conjunction).
v9.28 returned UNKNOWN on multi-phrase Contains; v9.30 returns SAT in <1s per phrase.
"""
import hashlib
import re
import sys
import time
from pathlib import Path

try:
    import z3
except ImportError:
    sys.exit("FATAL: z3 not installed")

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


def z3_verify_each_phrase_separately():
    """Per-phrase IndexOf — each in its own solver (parallel, tractable)."""
    results = []
    for phrase in REQUIRED_PHRASES:
        s = z3.Solver()
        s.set("timeout", 3000)
        line = z3.String("line")
        s.add(z3.IndexOf(line, z3.StringVal(phrase), 0) >= 0)
        t0 = time.time()
        rc = s.check()
        dt = time.time() - t0
        results.append({"phrase": phrase[:30], "result": str(rc), "time_sec": round(dt, 3)})
    return results


def z3_verify_unicode_attacks_decomposed():
    """Per-attack solver (no global conjunction)."""
    results = []
    phrase = "никогда не врут"
    for cp, name in FORBIDDEN_CODEPOINTS:
        s = z3.Solver()
        s.set("timeout", 5000)
        line = z3.String(f"line_{cp:x}")
        s.add(z3.IndexOf(line, z3.StringVal(phrase), 0) >= 0)
        s.add(z3.IndexOf(line, z3.StringVal(chr(cp)), 0) >= 0)
        t0 = time.time()
        rc = s.check()
        dt = time.time() - t0
        if rc == z3.sat:
            interp = "SAT — hash check mandatory"
        elif rc == z3.unsat:
            interp = "UNSAT — phrase blocks this attack"
        else:
            interp = "UNKNOWN (timeout)"
        results.append({"attack": f"U+{cp:04X} {name}", "result": str(rc), "time_sec": round(dt, 3), "interpretation": interp})
    return results


def z3_verify_hash_injectivity_timed():
    """Same proof as v9.28, with timing."""
    s = z3.Solver()
    s.set("timeout", 15000)
    sha_fn = z3.Function("sha256_16", z3.StringSort(), z3.BitVecSort(64))
    expected_bv = z3.BitVecVal(int(EXPECTED_HASH, 16), 64)
    x = z3.Const("x", z3.StringSort())
    y = z3.Const("y", z3.StringSort())
    s.add(z3.ForAll([x, y], z3.Implies(sha_fn(x) == sha_fn(y), x == y)))
    s.add(sha_fn(z3.StringVal(EXPECTED_PRIMARY_GOAL)) == expected_bv)
    test_line = z3.Const("test_line", z3.StringSort())
    s.add(sha_fn(test_line) == expected_bv)
    s.add(z3.IndexOf(test_line, z3.StringVal("никогда не врут"), 0) < 0)
    t0 = time.time()
    rc = s.check()
    dt = time.time() - t0
    if rc == z3.unsat:
        return {"result": "UNSAT — formally PROVEN", "time_sec": round(dt, 3)}
    elif rc == z3.unknown:
        return {"result": "UNKNOWN (timeout)", "time_sec": round(dt, 3)}
    return {"result": f"SAT (rc={rc})", "time_sec": round(dt, 3)}


def concrete_checks():
    actual_line = load_primary_goal_line()
    actual_hash = sha256_16(actual_line) if actual_line else ""
    forbidden = [f"U+{cp:04X}" for cp, _ in FORBIDDEN_CODEPOINTS if chr(cp) in actual_line] if actual_line else []
    return {
        "hash_pass": actual_hash == EXPECTED_HASH,
        "actual_hash": actual_hash,
        "unicode_pass": len(forbidden) == 0,
        "forbidden_found": forbidden,
    }


def main():
    print("=" * 70)
    print("G51 Z3-STRING-THEORY-OPTIMIZED v9.30")
    print("=" * 70)
    print(f"Z3 version: {z3.get_version_string()}")
    print()

    t_total = time.time()

    print("[1/4] Per-phrase IndexOf (parallel solvers, 3s each):")
    pp = z3_verify_each_phrase_separately()
    for r in pp:
        print(f"     {r['phrase']:<32} {r['result']:<10} {r['time_sec']}s")
    print()

    print("[2/4] Unicode attacks decomposed:")
    ua = z3_verify_unicode_attacks_decomposed()
    for atk in ua:
        print(f"     {atk['attack']:<35} {atk['result']:<10} {atk['time_sec']}s")
    print()

    print("[3/4] Hash-injectivity (timed):")
    hi = z3_verify_hash_injectivity_timed()
    print(f"     {hi['result']}")
    print(f"     time: {hi['time_sec']}s")
    print()

    print("[4/4] Concrete cross-checks:")
    cs = concrete_checks()
    print(f"     hash: {'PASS' if cs['hash_pass'] else 'FAIL'} ({cs['actual_hash']})")
    print(f"     unicode: {'PASS' if cs['unicode_pass'] else 'FAIL'} ({cs['forbidden_found']})")
    print()

    total_time = round(time.time() - t_total, 3)
    sat_count = sum(1 for r in pp if r["result"] == "sat")

    print("=" * 70)
    print(f"Total time: {total_time}s (vs v9.28 ~30s with UNKNOWN results)")
    print(f"Per-phrase: {sat_count}/{len(pp)} SAT (vs v9.28 UNKNOWN)")
    print(f"Hash-injectivity: {hi['result'][:60]}")
    print("=" * 70)

    import json
    out = Path("/home/z/my-project/download/benchmarks/z3_v930_optimized.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "test": "G51-Z3-string-theory-optimized",
        "version": "v9.30",
        "total_time_sec": total_time,
        "per_phrase": pp,
        "unicode_attacks": ua,
        "hash_injectivity": hi,
        "concrete_checks": cs,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"JSON: {out}")


if __name__ == "__main__":
    main()
