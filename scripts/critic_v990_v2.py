#!/usr/bin/env python3
"""
Критика v9.90-TRUTHGATE2 — обновлённые критики (учитывают что уже исправлено).
"""
import re
from pathlib import Path

PROMPT = Path("/home/z/my-project/repo/meta-prompt-v9.90-TRUTHGATE2.md").read_text()

issues = []

tg_section = PROMPT.split("§XI")[1] if "§XI" in PROMPT else ""

# C1: web_search fallback
if "UNVERIFIED-MAY-BE-OUTDATED" not in tg_section:
    issues.append(("HIGH", "C1: нет UNVERIFIED-MAY-BE-OUTDATED маркера для web_search недоступности", "Добавить"))

# C2: FALSE/DISPUTED claims
if "DISPUTED" not in tg_section:
    issues.append(("MEDIUM", "C2: TG не помечает DISPUTED claims", "Добавить [DISPUTED: source]"))

# C3: missing categories
missing = []
for cat in ["regulatory", "people", "DOI", "statistics"]:
    if cat.lower() not in tg_section.lower():
        missing.append(cat)
if missing:
    issues.append(("MEDIUM", f"C3: отсутствуют категории: {missing}", "Добавить"))

# C4: timeout/limit
if "max_claims" not in tg_section or "timeout" not in tg_section.lower():
    issues.append(("LOW", "C4: нет max_claims/timeout", "Добавить"))

# C5: cache TTL
if "cache_ttl" not in tg_section and "24h" not in tg_section:
    issues.append(("MEDIUM", "C5: нет cache_ttl для переверификации", "Добавить"))

# C6: NL-9 ссылается на §XI
if "См. §XI" not in PROMPT and "см. §XI" not in PROMPT.lower():
    issues.append(("LOW", "C6: NL-9 не ссылается на §XI", "Добавить ссылку"))

# C7: multi-source
if "Wikipedia" not in tg_section and "DuckDuckGo" not in tg_section:
    issues.append(("MEDIUM", "C7: TG не упоминает multi-source", "Добавить"))

# C8: TG-FAILED fallback
if "TG-FAILED" not in tg_section:
    issues.append(("LOW", "C8: нет TG-FAILED fallback", "Добавить"))

# C9: Qwen3 thinking mode
if "Qwen3" not in tg_section and "no_think" not in tg_section:
    issues.append(("LOW", "C9: Qwen3 thinking не упомянут", "Добавить"))

# C10: tg_version
if "tg_version" not in tg_section:
    issues.append(("LOW", "C10: нет tg_version", "Добавить"))

# C11: retry
if "retry" not in tg_section.lower():
    issues.append(("MEDIUM", "C11: нет retry", "Добавить"))

# C12: JSON-safe
if "verified_claims" not in tg_section:
    issues.append(("HIGH", "C12: нет JSON-safe verified_claims поля", "Добавить"))

# Новые критики для v9.90
# C13: нет примера DISPUTED
if "DISPUTED" in tg_section and "openai.com shows" not in tg_section:
    issues.append(("LOW", "C13: нет примера DISPUTED", "Добавить пример"))

# C14: нет описания что делает TG-FAILED
if "TG-FAILED" in tg_section and "verify manually" not in tg_section:
    issues.append(("LOW", "C14: нет описания TG-FAILED", "Уточнить"))

# Print
print("=" * 70)
print("КРИТИКА v9.90-TRUTHGATE2 (обновлённые критики)")
print("=" * 70)
for sev, name, fix in issues:
    icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🔵"}[sev]
    print(f"{icon} {name}")
    print(f"   Fix: {fix}\n")
print(f"ИТОГО: {len(issues)} проблем")
by_sev = {}
for s, _, _ in issues:
    by_sev[s] = by_sev.get(s, 0) + 1
for s in ["HIGH", "MEDIUM", "LOW"]:
    print(f"  {s}: {by_sev.get(s, 0)}")
