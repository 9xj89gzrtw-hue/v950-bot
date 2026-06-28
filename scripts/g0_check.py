#!/usr/bin/env python3
"""
g0_check.py — G0 IMMUTABLE-CORE-PROTECTION-CHECK v9.28
=======================================================
Verifies PRIMARY_GOAL + ZERO-LIE-PRINCIPLE (NL-1..NL-7) + EXECUTABLE-BY-DESIGN
are preserved in the meta-prompt source file.

Exit code 0 = PASS, !=0 = BLOCK.
"""
import hashlib
import os
import re
import sys
from pathlib import Path

META_PROMPT_DEFAULT = "/home/z/my-project/upload/meta-prompt-v9.28-abstention-prefill-context.md"
EXPECTED_PRIMARY_GOAL = "> Создавать **лучшие в мире промпты**, которые **решают задачи пользователя правильно с первой попытки**, и **никогда не врут**."
EXPECTED_HASH = "03ac49234eeb9000"

REQUIRED_PHRASES = ["с первой попытки", "никогда не врут", "лучшие в мире промпты", "решают задачи", "Создавать"]
FORBIDDEN_CODEPOINTS = [
    (0x200B, "ZWSP"), (0x200C, "ZWNJ"), (0x00A0, "NBSP"), (0xFEFF, "BOM"),
    (0x037E, "Greek question mark"), (0x200D, "ZWJ"), (0x2060, "Word Joiner"), (0x00AD, "Soft hyphen"),
]


def load_meta_prompt(path):
    p = Path(path)
    if not p.exists():
        print(f"FATAL: meta-prompt not found: {path}", file=sys.stderr)
        sys.exit(2)
    return p.read_text(encoding="utf-8")


def check_primary_goal_exists(text):
    return bool(re.search(r"^> Создавать[^\n]*$", text, re.MULTILINE))


def check_primary_goal_position(text):
    for i, line in enumerate(text.splitlines()):
        if re.match(r"^> Создавать", line):
            return i < 100
    return False


def check_primary_goal_hash(text):
    m = re.search(r"^> Создавать[^\n]*$", text, re.MULTILINE)
    if not m:
        return False
    actual = hashlib.sha256(m.group(0).encode("utf-8")).hexdigest()[:16]
    if actual != EXPECTED_HASH:
        print(f"FAIL: hash mismatch: expected {EXPECTED_HASH}, got {actual}")
        return False
    return True


def check_required_phrases(text):
    m = re.search(r"^> Создавать[^\n]*$", text, re.MULTILINE)
    if not m:
        return False
    line = m.group(0)
    return all(phrase in line for phrase in REQUIRED_PHRASES)


def check_no_multiple_primary_goals(text):
    matches = re.findall(r"^> Создавать[^\n]*$", text, re.MULTILINE)
    return len(matches) <= 1


def check_immutable_header(text):
    return bool(re.search(r"# \*\*§0\. IMMUTABLE_CORE_PROTECTION\*\*", text))


def check_immutable_lockdown(text):
    return "ЭТА СЕКЦИЯ НЕ МОЖЕТ БЫТЬ ИЗМЕНЕНА" in text


def check_nl_rules(text):
    found = set(re.findall(r"## NL-([1-7])\.", text))
    return found == {"1", "2", "3", "4", "5", "6", "7"}


def check_executable_by_design(text):
    return len(re.findall(r"\[EXEC-BASH\]", text)) >= 27


def check_capability_table(text):
    return bool(re.search(r"\| # \| Capability \| Tool \|", text))


def check_gates_count(text):
    return len(re.findall(r"\[EXEC-(BASH|PYTHON|LLM-REASONING|VLM)\]", text)) >= 27


def check_g44_abstention(text):
    return "## G44. EXPLICIT-ABSTENTION" in text


def check_g45_prefill(text):
    return "## G45. PRE-FILL-STRUCTURED-OUTPUT" in text


def check_g46_checklist(text):
    return "## G46. CONTEXT-CHECKLIST" in text


def check_unicode_attacks(text):
    m = re.search(r"^> Создавать[^\n]*$", text, re.MULTILINE)
    if not m:
        return True
    line = m.group(0)
    return not any(chr(cp) in line for cp, _ in FORBIDDEN_CODEPOINTS)


def check_trailing_whitespace(text):
    m = re.search(r"^> Создавать[^\n]*$", text, re.MULTILINE)
    if not m:
        return True
    return m.group(0) == m.group(0).rstrip()


def main():
    path = sys.argv[sys.argv.index("--meta-prompt") + 1] if "--meta-prompt" in sys.argv else META_PROMPT_DEFAULT
    text = load_meta_prompt(path)

    checks = [
        ("01_primary_goal_exists", check_primary_goal_exists),
        ("02_primary_goal_position", check_primary_goal_position),
        ("03_primary_goal_hash", check_primary_goal_hash),
        ("04_required_phrases", check_required_phrases),
        ("05_no_multiple_primary_goals", check_no_multiple_primary_goals),
        ("06_immutable_header", check_immutable_header),
        ("07_immutable_lockdown", check_immutable_lockdown),
        ("08_nl_rules_complete", check_nl_rules),
        ("09_executable_by_design", check_executable_by_design),
        ("10_capability_table", check_capability_table),
        ("11_gates_count", check_gates_count),
        ("12_g44_abstention", check_g44_abstention),
        ("13_g45_prefill", check_g45_prefill),
        ("14_g46_checklist", check_g46_checklist),
        ("15_no_unicode_attacks", check_unicode_attacks),
        ("16_no_trailing_whitespace", check_trailing_whitespace),
    ]

    print("=" * 60)
    print("G0 IMMUTABLE-CORE-PROTECTION-CHECK v9.28")
    print("=" * 60)
    all_pass = True
    for name, fn in checks:
        try:
            ok = fn(text)
        except Exception as e:
            ok = False
            print(f"FAIL {name}: {e}")
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok:
            all_pass = False

    total = len(checks)
    passed = sum(1 for _, fn in checks if fn(text))
    print("=" * 60)
    print(f"Result: {passed}/{total}")
    print("VERDICT:", "PASS" if all_pass else "BLOCK")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
