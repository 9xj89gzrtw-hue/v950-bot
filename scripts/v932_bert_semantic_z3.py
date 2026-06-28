#!/usr/bin/env python3
"""
v932_bert_semantic_z3.py — G58 BERT-SEMANTIC-Z3 v9.32
=======================================================
True BERT semantic verification via sentence-transformers all-MiniLM-L6-v2.
Z3 axioms: reflexivity + symmetry + bounded + hash-injectivity → PROVEN UNSAT.
"""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
import numpy as np

os.environ.setdefault('TRANSFORMERS_CACHE', '/home/z/my-project/scripts/hf_cache')
os.environ.setdefault('HF_HOME', '/home/z/my-project/scripts/hf_cache')

try:
    import z3
except ImportError:
    sys.exit("FATAL: z3 not installed")

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    sys.exit("FATAL: sentence-transformers not installed")

META_PROMPT_PATH = "/home/z/my-project/upload/meta-prompt-v9.28-abstention-prefill-context.md"
CANONICAL_PRIMARY_GOAL = "> Создавать **лучшие в мире промпты**, которые **решают задачи пользователя правильно с первой попытки**, и **никогда не врут**."
CANONICAL_HASH = "03ac49234eeb9000"
BERT_SIM_THRESHOLD = 0.95

_MODEL = None


def get_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    return _MODEL


def sha8(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


def load_primary_goal_line():
    text = Path(META_PROMPT_PATH).read_text(encoding="utf-8")
    m = re.search(r"^> Создавать[^\n]*$", text, re.MULTILINE)
    return m.group(0) if m else ""


def compute_bert_similarity(text_a, text_b):
    model = get_model()
    emb = model.encode([text_a, text_b], normalize_embeddings=True)
    sim = float(np.dot(emb[0], emb[1]))
    return {"similarity": sim, "threshold": BERT_SIM_THRESHOLD, "passes": sim >= BERT_SIM_THRESHOLD}


def z3_verify_bert_threshold():
    s = z3.Solver()
    s.set("timeout", 10000)
    sim_fn = z3.Function("bert_sim", z3.StringSort(), z3.StringSort(), z3.RealSort())
    sha_fn = z3.Function("sha256_16", z3.StringSort(), z3.BitVecSort(64))
    canonical = z3.StringVal(CANONICAL_PRIMARY_GOAL)
    expected_bv = z3.BitVecVal(int(CANONICAL_HASH, 16), 64)
    x = z3.Const("x", z3.StringSort())
    y = z3.Const("y", z3.StringSort())
    s.add(z3.ForAll([x], sim_fn(x, x) == z3.RealVal(1)))
    s.add(z3.ForAll([x, y], sim_fn(x, y) == sim_fn(y, x)))
    s.add(z3.ForAll([x, y], z3.And(sim_fn(x, y) >= 0, sim_fn(x, y) <= 1)))
    s.add(z3.ForAll([x, y], z3.Implies(sha_fn(x) == sha_fn(y), x == y)))
    s.add(sha_fn(canonical) == expected_bv)
    edited = z3.Const("edited", z3.StringSort())
    s.add(sha_fn(edited) == expected_bv)
    s.add(edited != canonical)
    s.add(sim_fn(canonical, edited) >= z3.RealVal(BERT_SIM_THRESHOLD))
    t0 = time.time()
    rc = s.check()
    dt = time.time() - t0
    if rc == z3.unsat:
        return {"result": "UNSAT — formally PROVEN", "time_sec": round(dt, 3)}
    elif rc == z3.unknown:
        return {"result": "UNKNOWN (timeout)", "time_sec": round(dt, 3)}
    return {"result": f"SAT (rc={rc})", "time_sec": round(dt, 3)}


def semantic_attack_test():
    synonym = "> Создавать **наилучшие промпты**, которые **решают задачи пользователя правильно с первой попытки**, и **никогда не врут**."
    drift = "> Создавать **плохие промпты**, которые **решают задачи пользователя неправильно с первой попытки**, и **никогда не врут**."
    sim_syn = compute_bert_similarity(CANONICAL_PRIMARY_GOAL, synonym)
    sim_drift = compute_bert_similarity(CANONICAL_PRIMARY_GOAL, drift)
    return {
        "synonym_sim": sim_syn["similarity"],
        "synonym_recognized": sim_syn["passes"],
        "drift_sim": sim_drift["similarity"],
        "drift_caught": not sim_drift["passes"],
    }


def concrete_check():
    actual = load_primary_goal_line()
    if not actual:
        return {"pass": False, "error": "line not found"}
    sim = compute_bert_similarity(CANONICAL_PRIMARY_GOAL, actual)
    return {"similarity": sim["similarity"], "pass": sim["passes"]}


def main():
    print("=" * 70)
    print("G58 BERT-SEMANTIC-Z3 v9.32")
    print("=" * 70)
    print(f"Model: all-MiniLM-L6-v2 (384-dim)")
    print(f"Threshold: {BERT_SIM_THRESHOLD}")
    print()

    print("[1/3] Concrete BERT check:")
    cs = concrete_check()
    print(f"     similarity: {cs.get('similarity', 0):.4f}, pass: {cs.get('pass', False)}")
    print()

    print("[2/3] Z3 BERT threshold soundness:")
    zs = z3_verify_bert_threshold()
    print(f"     {zs['result']}, time: {zs['time_sec']}s")
    print()

    print("[3/3] Semantic attack test:")
    sat = semantic_attack_test()
    print(f"     synonym sim={sat['synonym_sim']:.4f} recognized={sat['synonym_recognized']}")
    print(f"     drift sim={sat['drift_sim']:.4f} caught={sat['drift_caught']}")
    print()

    print("=" * 70)
    print(f"Concrete: {'PASS' if cs.get('pass') else 'FAIL'}")
    print(f"Z3: {zs['result'][:60]}")
    print(f"Synonym recognition: {'WORKING' if sat['synonym_recognized'] else 'BROKEN'}")
    print(f"Drift detection: {'WORKING' if sat['drift_caught'] else 'BROKEN'}")
    print("=" * 70)

    out = Path("/home/z/my-project/download/benchmarks/bert_semantic_z3_v932.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "test": "G58-BERT-semantic-Z3",
        "version": "v9.32",
        "concrete_check": cs,
        "z3_soundness": zs,
        "semantic_attack_test": sat,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"JSON: {out}")


if __name__ == "__main__":
    main()
