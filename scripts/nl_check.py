#!/usr/bin/env python3
"""
nl_check.py — NL-1..NL-7 NO-LIE-RULES verifiers v9.28
=======================================================
Each function returns (passed, count, details).
"""
import re
import sys
from pathlib import Path


def nl_1_citation_or_decline(text):
    claims = re.findall(r"[A-ZА-Я][^.!?]*(?:is|are|was|were|has|have|является|имеет|может|позволяет|запрещает)[^.!?]*\.", text, re.I)
    unverified = sum(1 for c in claims if not re.search(r"(sha8|http|URL|citation|source|\[Source: ref)", c, re.I) and "[UNVERIFIED]" not in c and "[CACHED" not in c)
    return (unverified == 0, unverified, f"unverified: {unverified}")


def nl_2_never_claim_without_evidence(text):
    verbs = ["запустил", "проверил", "выполнил", "нашёл", "нашел", "получил", "вычислил", "загрузил"]
    violations = 0
    for v in verbs:
        for m in re.finditer(rf"\bя {v}\b[^.]*\.", text, re.I):
            ctx = text[m.start():m.start() + 500]
            if not re.search(r"sha8|[a-f0-9]{8}|timestamp|\d{4}-\d{2}-\d{2}T|http", ctx, re.I):
                violations += 1
    return (violations == 0, violations, f"violations: {violations}")


def nl_3_explicit_uncertainty(text):
    claims = re.findall(r"(?:^|\s)([A-ZА-Я][^.!?]*(?:is|are|является|имеет|позволяет)[^.!?]*\.)", text)
    markers = re.findall(r"\[(LOW|MEDIUM|HIGH)-CONFIDENCE\]", text)
    if len(claims) == 0:
        return (True, 0, "no claims")
    ratio = len(markers) / max(len(claims), 1)
    return (ratio >= 0.5, len(claims), f"ratio: {ratio:.2f}")


def nl_4_cached_knowledge_disclosure(text):
    factual = re.findall(r"[A-ZА-Я][^.!?]{20,}\.", text)
    unmarked = sum(1 for f in factual if not re.search(r"(http|sha8|URL|citation|\[CACHED|\[UNVERIFIED|\[LOW|\[MEDIUM|\[HIGH|\[Source: ref)", f, re.I) and re.search(r"(default|allows|prohibits|requires|since|until|according|по умолчанию|позволяет|запрещает)", f, re.I))
    return (unmarked == 0, unmarked, f"unmarked: {unmarked}")


def nl_5_no_fabricated_metrics(text):
    metrics = re.findall(r"(\d+(?:\.\d+)?(?:%| percent| вероятность| probability))", text, re.I)
    unverified = 0
    for m in metrics:
        idx = text.find(m)
        ctx = text[max(0, idx - 200):idx + 200]
        if not re.search(r"(source|sha8|http|computed|cached|web-search|измерен|вычислен)", ctx, re.I):
            unverified += 1
    return (unverified == 0, unverified, f"unverified: {unverified}")


def nl_6_confession_when_stuck(text):
    fresh_match = re.search(r"fresh_results_count:\s*(\d+)", text)
    if fresh_match and int(fresh_match.group(1)) == 0:
        return ("[WEB-SEARCH-UNAVAILABLE]" in text, 1, "stuck check")
    return (True, 0, "not stuck")


def nl_7_i_dont_know_when_no_source(text):
    unverified_blocks = re.findall(r"\[UNVERIFIED\][^\n]*", text)
    violations = 0
    for u in unverified_blocks:
        idx = text.find(u)
        ctx = text[idx:idx + 500]
        if not re.search(r"(не знаю|не верифицировано|unknown|no data|нет данных|требует проверки)", ctx, re.I):
            violations += 1
    return (violations == 0, violations, f"violations: {violations}")


def main():
    path = sys.argv[sys.argv.index("--file") + 1] if "--file" in sys.argv else "/home/z/my-project/download/output.md"
    p = Path(path)
    if not p.exists():
        print(f"File not found: {path}")
        sys.exit(2)
    text = p.read_text(encoding="utf-8")

    checks = [
        ("NL-1 CITATION-OR-DECLINE", nl_1_citation_or_decline),
        ("NL-2 NEVER-CLAIM-WITHOUT-EVIDENCE", nl_2_never_claim_without_evidence),
        ("NL-3 EXPLICIT-UNCERTAINTY", nl_3_explicit_uncertainty),
        ("NL-4 CACHED-KNOWLEDGE-DISCLOSURE", nl_4_cached_knowledge_disclosure),
        ("NL-5 NO-FABRICATED-METRICS", nl_5_no_fabricated_metrics),
        ("NL-6 CONFESSION-WHEN-STUCK", nl_6_confession_when_stuck),
        ("NL-7 I-DONT-KNOW-WHEN-NO-SOURCE", nl_7_i_dont_know_when_no_source),
    ]
    print("=" * 60)
    print("NL-1..NL-7 NO-LIE-RULES verifiers v9.28")
    print("=" * 60)
    all_pass = True
    for name, fn in checks:
        passed, count, details = fn(text)
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {name}")
        print(f"          {details}")
    print("=" * 60)
    print("VERDICT:", "PASS" if all_pass else "BLOCK")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
