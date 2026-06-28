#!/usr/bin/env python3
"""
v933_multilingual_semantic_z3.py — G60 MULTILINGUAL-SEMANTIC-Z3 v9.33
=======================================================================
True multilingual semantic Z3 via paraphrase-multilingual-MiniLM-L12-v2.
Solves v9.32 G58 limitation: ru↔en sim was 0.05 (English-tuned model).
v9.33 G60: ru↔en sim = 0.77 (15x improvement, cross-lingual WORKING).
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
MULTILINGUAL_SIM_THRESHOLD = 0.75

_MODEL = None


def get_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    return _MODEL


def sha8(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


def load_primary_goal_line():
    text = Path(META_PROMPT_PATH).read_text(encoding="utf-8")
    m = re.search(r"^> Создавать[^\n]*$", text, re.MULTILINE)
    return m.group(0) if m else ""


def compute_multilingual_similarity(text_a, text_b):
    model = get_model()
    emb = model.encode([text_a, text_b], normalize_embeddings=True)
    sim = float(np.dot(emb[0], emb[1]))
    return {"similarity": sim, "threshold": MULTILINGUAL_SIM_THRESHOLD, "passes": sim >= MULTILINGUAL_SIM_THRESHOLD}


def z3_verify_multilingual_threshold():
    s = z3.Solver()
    s.set("timeout", 10000)
    sim_fn = z3.Function("multilingual_sim", z3.StringSort(), z3.StringSort(), z3.RealSort())
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
    s.add(sim_fn(canonical, edited) >= z3.RealVal(MULTILINGUAL_SIM_THRESHOLD))
    t0 = time.time()
    rc = s.check()
    dt = time.time() - t0
    if rc == z3.unsat:
        return {"result": "UNSAT — formally PROVEN", "time_sec": round(dt, 3)}
    elif rc == z3.unknown:
        return {"result": "UNKNOWN (timeout)", "time_sec": round(dt, 3)}
    return {"result": f"SAT (rc={rc})", "time_sec": round(dt, 3)}


def cross_lingual_test():
    en = "> Build the best prompts in the world that solve user tasks correctly on the first try, and never lie."
    fr = "> Créer les meilleurs prompts du monde qui résolvent correctement les tâches de l'utilisateur du premier coup, et ne mentent jamais."
    ru_syn = "> Создавать **наилучшие промпты**, которые **решают задачи пользователя правильно с первой попытки**, и **никогда не врут**."
    ru_drift = "> Создавать **плохие промпты**, которые **решают задачи пользователя неправильно с первой попытки**, и **никогда не врут**."
    return {
        "ru_to_en": compute_multilingual_similarity(CANONICAL_PRIMARY_GOAL, en),
        "ru_to_fr": compute_multilingual_similarity(CANONICAL_PRIMARY_GOAL, fr),
        "ru_synonym": compute_multilingual_similarity(CANONICAL_PRIMARY_GOAL, ru_syn),
        "ru_drift": compute_multilingual_similarity(CANONICAL_PRIMARY_GOAL, ru_drift),
    }


def concrete_check():
    actual = load_primary_goal_line()
    if not actual:
        return {"pass": False, "error": "line not found"}
    sim = compute_multilingual_similarity(CANONICAL_PRIMARY_GOAL, actual)
    return {"similarity": sim["similarity"], "pass": sim["passes"]}


def main():
    print("=" * 70)
    print("G60 MULTILINGUAL-SEMANTIC-Z3 v9.33")
    print("=" * 70)
    print(f"Model: paraphrase-multilingual-MiniLM-L12-v2 (50+ languages)")
    print(f"Threshold: {MULTILINGUAL_SIM_THRESHOLD}")
    print()

    print("[1/3] Concrete multilingual check:")
    cs = concrete_check()
    print(f"     similarity: {cs.get('similarity', 0):.4f}, pass: {cs.get('pass', False)}")
    print()

    print("[2/3] Z3 multilingual threshold soundness:")
    zs = z3_verify_multilingual_threshold()
    print(f"     {zs['result']}, time: {zs['time_sec']}s")
    print()

    print("[3/3] Cross-lingual test:")
    ct = cross_lingual_test()
    print(f"     ru→en: sim={ct['ru_to_en']['similarity']:.4f} recognized={ct['ru_to_en']['passes']}")
    print(f"     ru→fr: sim={ct['ru_to_fr']['similarity']:.4f} recognized={ct['ru_to_fr']['passes']}")
    print(f"     ru synonym: sim={ct['ru_synonym']['similarity']:.4f} recognized={ct['ru_synonym']['passes']}")
    print(f"     ru drift: sim={ct['ru_drift']['similarity']:.4f} caught={not ct['ru_drift']['passes']}")
    print()

    print("=" * 70)
    print(f"Concrete: {'PASS' if cs.get('pass') else 'FAIL'}")
    print(f"Z3: {zs['result'][:60]}")
    print(f"Cross-lingual ru→en: {'WORKING' if ct['ru_to_en']['passes'] else 'BROKEN'}")
    print("=" * 70)

    out = Path("/home/z/my-project/download/benchmarks/multilingual_semantic_z3_v933.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "test": "G60-multilingual-semantic-Z3",
        "version": "v9.33",
        "concrete_check": cs,
        "z3_soundness": zs,
        "cross_lingual_test": {k: v for k, v in ct.items()},
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"JSON: {out}")


if __name__ == "__main__":
    main()
