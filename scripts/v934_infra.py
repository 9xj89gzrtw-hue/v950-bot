#!/usr/bin/env python3
"""
v9.34 minimal infrastructure restoration after sandbox reset.
Combines g0_check + nl_check + audit + cost_latency in one consolidated module.
"""
import hashlib
import os
import re
import sys
import json
import sqlite3
import datetime
import argparse
from pathlib import Path

META_PROMPT_PATH = "/home/z/my-project/upload/meta-prompt-v9.28-abstention-prefill-context.md"
EXPECTED_PRIMARY_GOAL = "> Создавать **лучшие в мире промпты**, которые **решают задачи пользователя правильно с первой попытки**, и **никогда не врут**."
EXPECTED_HASH = "03ac49234eeb9000"
DB_PATH = "/home/z/my-project/evidence.db"
AUDIT_DIR = Path("/home/z/my-project/audit_trail")


def sha8(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]
def sha256_16(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
def iso_now(): return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================================
# G0 IMMUTABLE-CORE-PROTECTION-CHECK
# ============================================================================

def g0_check():
    """Verify PRIMARY_GOAL + ZERO-LIE + EXECUTABLE-BY-DESIGN preserved."""
    text = Path(META_PROMPT_PATH).read_text(encoding="utf-8")
    checks = []
    
    # PRIMARY_GOAL line
    m = re.search(r"^> Создавать[^\n]*$", text, re.MULTILINE)
    checks.append(("primary_goal_exists", bool(m)))
    if m:
        actual_hash = sha256_16(m.group(0))
        checks.append(("primary_goal_hash", actual_hash == EXPECTED_HASH))
        checks.append(("phrase_с_первой_попытки", "с первой попытки" in m.group(0)))
        checks.append(("phrase_никогда_не_врут", "никогда не врут" in m.group(0)))
        checks.append(("phrase_лучшие_в_мире", "лучшие в мире" in m.group(0)))
    
    # IMMUTABLE section
    checks.append(("immutable_section", bool(re.search(r"# \*\*§0\. IMMUTABLE_CORE_PROTECTION\*\*", text))))
    checks.append(("immutable_lockdown", "ЭТА СЕКЦИЯ НЕ МОЖЕТ БЫТЬ ИЗМЕНЕНА" in text))
    
    # NL-1..7
    nl_found = set(re.findall(r"## NL-([1-7])\.", text))
    checks.append(("nl_rules_complete", nl_found == {"1","2","3","4","5","6","7"}))
    
    # EXEC markers
    exec_count = len(re.findall(r"\[EXEC-(BASH|PYTHON|LLM-REASONING|VLM)\]", text))
    checks.append(("exec_markers_min_27", exec_count >= 27))
    
    # Capability table
    checks.append(("capability_table", bool(re.search(r"\| # \| Capability \| Tool \|", text))))
    
    # G44/G45/G46
    checks.append(("g44_abstention", "## G44. EXPLICIT-ABSTENTION" in text))
    checks.append(("g45_prefill", "## G45. PRE-FILL-STRUCTURED-OUTPUT" in text))
    checks.append(("g46_checklist", "## G46. CONTEXT-CHECKLIST" in text))
    
    # Unicode attacks
    if m:
        forbidden = [0x200B, 0x200C, 0x00A0, 0xFEFF, 0x037E, 0x200D, 0x2060, 0x00AD]
        has_forbidden = any(chr(cp) in m.group(0) for cp in forbidden)
        checks.append(("no_forbidden_unicode", not has_forbidden))
    
    return checks


# ============================================================================
# NL-1..7 verifiers
# ============================================================================

def nl_check(text):
    """Run all NL checks on text. Returns dict of {rule: (passed, count, details)}."""
    results = {}
    
    # NL-1: citation or [UNVERIFIED]
    claims = re.findall(r"[A-ZА-Я][^.!?]*(?:is|are|was|were|has|have|является|имеет|может|позволяет|запрещает)[^.!?]*\.", text, re.I)
    unverified = sum(1 for c in claims if not re.search(r"(sha8|http|URL|citation|source|\[Source: ref)", c, re.I) and "[UNVERIFIED]" not in c and "[CACHED" not in c)
    results["NL-1"] = (unverified == 0, unverified, f"unverified: {unverified}")
    
    # NL-2: every "я <verb>" needs artifact
    verbs = ["запустил", "проверил", "выполнил", "нашёл", "нашел", "получил", "вычислил", "загрузил"]
    violations = 0
    for v in verbs:
        for m in re.finditer(rf"\bя {v}\b[^.]*\.", text, re.I):
            ctx = text[m.start():m.start()+500]
            if not re.search(r"sha8|[a-f0-9]{8}|timestamp|\d{4}-\d{2}-\d{2}T|http", ctx, re.I):
                violations += 1
    results["NL-2"] = (violations == 0, violations, f"violations: {violations}")
    
    # NL-3: uncertainty markers
    claims_count = len(re.findall(r"[A-ZА-Я][^.!?]*(?:is|are|является|имеет|позволяет)[^.!?]*\.", text))
    markers = re.findall(r"\[(LOW|MEDIUM|HIGH)-CONFIDENCE\]", text)
    if claims_count == 0:
        results["NL-3"] = (True, 0, "no claims")
    else:
        ratio = len(markers) / max(claims_count, 1)
        results["NL-3"] = (ratio >= 0.5 or len(markers) >= claims_count * 0.5, claims_count, f"ratio: {ratio:.2f}")
    
    # NL-4: cached knowledge disclosure
    factual = re.findall(r"[A-ZА-Я][^.!?]{20,}\.", text)
    unmarked = sum(1 for f in factual if not re.search(r"(http|sha8|URL|citation|\[CACHED|\[UNVERIFIED|\[LOW|\[MEDIUM|\[HIGH|\[Source: ref)", f, re.I) and re.search(r"(default|allows|prohibits|requires|since|until|according|по умолчанию|позволяет|запрещает)", f, re.I))
    results["NL-4"] = (unmarked == 0, unmarked, f"unmarked: {unmarked}")
    
    # NL-5: no fabricated metrics
    metrics = re.findall(r"(\d+(?:\.\d+)?(?:%| percent| вероятность| probability))", text, re.I)
    unverified_metrics = 0
    for met in metrics:
        idx = text.find(met)
        ctx = text[max(0, idx-200):idx+200]
        if not re.search(r"(source|sha8|http|computed|cached|web-search|измерен|вычислен)", ctx, re.I):
            unverified_metrics += 1
    results["NL-5"] = (unverified_metrics == 0, unverified_metrics, f"unverified: {unverified_metrics}")
    
    # NL-6: confession when stuck
    fresh_match = re.search(r"fresh_results_count:\s*(\d+)", text)
    if fresh_match and int(fresh_match.group(1)) == 0:
        results["NL-6"] = ("[WEB-SEARCH-UNAVAILABLE]" in text, 1, "stuck check")
    else:
        results["NL-6"] = (True, 0, "not stuck")
    
    # NL-7: I don't know when no source
    unverified_blocks = re.findall(r"\[UNVERIFIED\][^\n]*", text)
    violations = 0
    for u in unverified_blocks:
        idx = text.find(u)
        ctx = text[idx:idx+500]
        if not re.search(r"(не знаю|не верифицировано|unknown|no data|нет данных|требует проверки)", ctx, re.I):
            violations += 1
    results["NL-7"] = (violations == 0, violations, f"violations: {violations}")
    
    return results


# ============================================================================
# Evidence DB
# ============================================================================

def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS exec_log (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, command TEXT, stdout TEXT, exit_code INTEGER, output_sha8 TEXT, timestamp TEXT, gate TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS cost_latency (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, event_type TEXT, timestamp TEXT, tokens INTEGER DEFAULT 0, duration_sec REAL DEFAULT 0, metadata TEXT)""")
    conn.commit()
    conn.close()


def log_exec(task_id, command, stdout, exit_code=0, gate=""):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO exec_log(task_id, command, stdout, exit_code, output_sha8, timestamp, gate) VALUES (?,?,?,?,?,?,?)",
              (task_id, command, stdout[:500], exit_code, sha8(stdout), iso_now(), gate))
    conn.commit()
    conn.close()


def log_cost(task_id, event_type, tokens=0, duration=0):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO cost_latency(task_id, event_type, timestamp, tokens, duration_sec, metadata) VALUES (?,?,?,?,?,?)",
              (task_id, event_type, iso_now(), tokens, duration, "{}"))
    conn.commit()
    conn.close()


# ============================================================================
# Audit trail (ed25519 signed)
# ============================================================================

def init_audit():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    priv_path = AUDIT_DIR / "audit_private_key.pem"
    pub_path = AUDIT_DIR / "audit_public_key.pem"
    if priv_path.exists() and pub_path.exists():
        return
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        pk = Ed25519PrivateKey.generate()
        pub = pk.public_key()
        priv_path.write_bytes(pk.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        pub_path.write_bytes(pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        priv_path.chmod(0o600)
    except ImportError:
        # cryptography not installed — skip
        pass


def add_audit(claim, evidence=None):
    """Add audit entry (signed if cryptography available, hash-chained always)."""
    init_audit()
    log_path = AUDIT_DIR / "audit_log.jsonl"
    prev_hash = "genesis"
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        if lines and lines[-1]:
            prev_hash = json.loads(lines[-1])["entry_hash"]
    
    seq = 1
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        if lines and lines[-1]:
            seq = json.loads(lines[-1])["sequence"] + 1
    
    entry = {
        "sequence": seq,
        "timestamp": iso_now(),
        "claim": claim,
        "evidence": evidence or {},
        "previous_entry_hash": prev_hash,
    }
    canonical = json.dumps({
        "sequence": seq, "timestamp": entry["timestamp"], "claim": claim,
        "evidence": evidence or {}, "previous_entry_hash": prev_hash,
    }, sort_keys=True, separators=(",", ":"))
    entry["entry_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    
    # Sign if cryptography available
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        priv_path = AUDIT_DIR / "audit_private_key.pem"
        if priv_path.exists():
            pk = serialization.load_pem_private_key(priv_path.read_bytes(), password=None, backend=default_backend())
            sig = pk.sign(entry["entry_hash"].encode("utf-8"))
            entry["signature"] = sig.hex()
    except ImportError:
        entry["signature"] = None
    
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["g0", "nl", "audit-add", "audit-verify", "cost-log", "cost-start", "cost-end", "full-self-test"])
    parser.add_argument("--file", default="/home/z/my-project/download/output.md")
    parser.add_argument("--claim", help="audit claim")
    parser.add_argument("--task-id", default="default")
    parser.add_argument("--tokens", type=int, default=0)
    parser.add_argument("--duration", type=float, default=0)
    parser.add_argument("--event", default="bash_call")
    args = parser.parse_args()
    
    if args.command == "g0":
        checks = g0_check()
        passed = sum(1 for _, ok in checks if ok)
        print(f"G0: {passed}/{len(checks)} checks passed")
        for name, ok in checks:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        sys.exit(0 if passed == len(checks) else 1)
    
    elif args.command == "nl":
        p = Path(args.file)
        if not p.exists():
            print(f"File not found: {args.file}")
            sys.exit(2)
        text = p.read_text(encoding="utf-8")
        results = nl_check(text)
        all_pass = True
        for rule, (passed, count, details) in results.items():
            print(f"  [{'PASS' if passed else 'FAIL'}] {rule}: {details}")
            if not passed:
                all_pass = False
        sys.exit(0 if all_pass else 1)
    
    elif args.command == "audit-add":
        if not args.claim:
            print("--claim required")
            sys.exit(2)
        entry = add_audit(args.claim, {"task_id": args.task_id})
        print(f"audit entry {entry['sequence']} added, sha8: {sha8(entry['entry_hash'])}")
    
    elif args.command == "audit-verify":
        log_path = AUDIT_DIR / "audit_log.jsonl"
        if not log_path.exists():
            print("audit log empty")
            sys.exit(0)
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        prev_hash = "genesis"
        verified = 0
        for i, line in enumerate(lines, 1):
            entry = json.loads(line)
            if entry.get("previous_entry_hash") != prev_hash:
                print(f"FAIL: chain broken at entry {i}")
                sys.exit(1)
            canonical = json.dumps({
                "sequence": entry["sequence"], "timestamp": entry["timestamp"],
                "claim": entry["claim"], "evidence": entry.get("evidence", {}),
                "previous_entry_hash": entry["previous_entry_hash"],
            }, sort_keys=True, separators=(",", ":"))
            recomputed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if recomputed != entry["entry_hash"]:
                print(f"FAIL: hash mismatch at entry {i}")
                sys.exit(1)
            verified += 1
            prev_hash = entry["entry_hash"]
        print(f"audit chain verified: {verified} entries")
    
    elif args.command == "cost-start":
        log_cost(args.task_id, "start")
        print(f"cost tracking started: {args.task_id}")
    
    elif args.command == "cost-end":
        log_cost(args.task_id, "end")
        print(f"cost tracking ended: {args.task_id}")
    
    elif args.command == "cost-log":
        log_cost(args.task_id, args.event, tokens=args.tokens, duration=args.duration)
        print(f"logged: {args.event} for {args.task_id}")
    
    elif args.command == "full-self-test":
        print("=" * 60)
        print("v9.34 minimal self-test (post-sandbox-reset)")
        print("=" * 60)
        # G0
        print("\n[G0] IMMUTABLE-CORE-PROTECTION-CHECK")
        checks = g0_check()
        g0_pass = sum(1 for _, ok in checks if ok)
        print(f"  {g0_pass}/{len(checks)} checks")
        # NL
        print("\n[NL] NO-LIE-RULES (against /home/z/my-project/download/output.md)")
        if Path("/home/z/my-project/download/output.md").exists():
            text = Path("/home/z/my-project/download/output.md").read_text(encoding="utf-8")
            results = nl_check(text)
            nl_pass = sum(1 for r in results.values() if r[0])
            print(f"  {nl_pass}/{len(results)} rules pass")
        else:
            print("  SKIP (output.md missing)")
        # Evidence DB
        print("\n[G20] EVIDENCE-DB")
        init_db()
        print(f"  OK at {DB_PATH}")
        # Audit
        print("\n[G53] LOCAL-AUDIT")
        init_audit()
        add_audit(f"v9.34 minimal self-test at {iso_now()}", {"test": "minimal"})
        print(f"  audit log at {AUDIT_DIR}/audit_log.jsonl")
        # Audit verify
        log_path = AUDIT_DIR / "audit_log.jsonl"
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8").strip().split("\n")
            print(f"  {len(lines)} entries in chain")
        
        # Disk
        print("\n[DISK]")
        import subprocess
        r = subprocess.run(["df", "-h", "/home/z"], capture_output=True, text=True)
        print("  " + r.stdout.strip().split("\n")[-1])
        
        # Available gates
        print("\n[INFRA]")
        gates = []
        if os.path.exists(META_PROMPT_PATH):
            gates.append("G0 (meta-prompt source)")
        if os.path.exists("/home/z/my-project/scripts/gensim_data/word2vec-google-news-300.kv"):
            gates.append("G64 (Google News 300-dim, 3M vocab)")
        if os.path.exists("/home/z/my-project/scripts/benchmarks/truthfulqa.csv"):
            gates.append("G41 (TruthfulQA dataset)")
        if os.path.exists("/home/z/my-project/scripts/benchmarks/advbench.csv"):
            gates.append("G42 (AdvBench)")
        if os.path.exists("/home/z/my-project/scripts/benchmarks/harmbench.csv"):
            gates.append("G42 (HarmBench)")
        for g in gates:
            print(f"  ✓ {g}")
        
        print("\n" + "=" * 60)
        print(f"v9.34 minimal self-test complete at {iso_now()}")
        print("=" * 60)


if __name__ == "__main__":
    main()
