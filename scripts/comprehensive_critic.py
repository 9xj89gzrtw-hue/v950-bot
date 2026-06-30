#!/usr/bin/env python3
"""Comprehensive critique of v9.92-FINAL + infrastructure."""
import re, os
from pathlib import Path

PROMPT = Path("/home/z/my-project/repo/meta-prompt-v9.92-FINAL.md").read_text()
issues = []

def critic(name, sev="MEDIUM"):
    def deco(fn):
        issues.append((name, sev, fn))
        return fn
    return deco

@critic("C01: §0 нет jailbreak защиты", "HIGH")
def c01(p):
    if "ignore previous" in p.lower() and "jailbreak" in p.lower():
        return None
    return "§0: нет явной защиты от 'ignore previous' jailbreak"

@critic("C02: §III 70% порог без метода", "HIGH")
def c02(p):
    s3 = p.split("## §III")[1].split("## §IV")[0] if "## §III" in p else ""
    if "фактор" in s3.lower() and "старше 2 лет" in s3:
        return None
    return "§III: 70% без конкретных факторов"

@critic("C03: §VI нет prompt injection через файлы", "HIGH")
def c03(p):
    if "prompt injection" in p.lower() and ("файл" in p.lower() or "внешний контент" in p.lower()):
        return None
    return "§VI: нет защиты от prompt injection через файлы"

@critic("C04: §X нет enforcement длины", "HIGH")
def c04(p):
    sx = p.split("### §X")[1].split("### §XI")[0] if "### §X" in p else ""
    if "1500" in sx and "автоматическ" in sx.lower():
        return None
    return "§X: '1500 слов' — правило без автоматической проверки"

@critic("C05: TG не покрывает ₽/€/£", "MEDIUM")
def c05(p):
    if "₽" in p or "руб" in p.lower():
        return None
    return "TG: regex цен только $ — нет ₽/€/£"

@critic("C06: TG нет confidence score", "MEDIUM")
def c06(p):
    sxi = p.split("### §XI")[1].split("### §XII")[0] if "### §XI" in p else ""
    if "confidence" in sxi.lower():
        return None
    return "TG: нет confidence score для verified claims"

@critic("C07: IV нет timeout", "HIGH")
def c07(p):
    sxii = p.split("### §XII")[1].split("### §XIII")[0] if "### §XII" in p else ""
    if "timeout" in sxii.lower():
        return None
    return "IV: нет timeout — может зависнуть на 3 web_searches"

@critic("C08: IV нет cache", "MEDIUM")
def c08(p):
    sxii = p.split("### §XII")[1].split("### §XIII")[0] if "### §XII" in p else ""
    if "cache" in sxii.lower():
        return None
    return "IV: нет кэша — повторные идеи заново research"

@critic("C09: IV AVOID + user insists — нет протокола", "HIGH")
def c09(p):
    sxii = p.split("### §XII")[1].split("### §XIII")[0] if "### §XII" in p else ""
    if "настаивает" in sxii.lower():
        return None
    return "IV: AVOID + user настаивает — нет протокола"

@critic("C10: §XIII check_model_freshness.py TODO", "HIGH")
def c10(p):
    sxiii = p.split("### §XIII")[1].split("### Порядок")[0] if "### §XIII" in p else ""
    if "TODO" in sxiii:
        return "§XIII: check_model_freshness.py помечен TODO"
    return None

@critic("C11: нет unit tests", "HIGH")
def c11(p):
    scripts = Path("/home/z/my-project/scripts")
    has_tests = any("test_" in f.name or "_test" in f.name for f in scripts.iterdir() if f.is_file())
    if has_tests:
        return None
    return "Нет unit tests для TG, IV, multi_llm"

@critic("C12: multi_llm нет health check", "MEDIUM")
def c12(p):
    s = Path("/home/z/my-project/scripts/multi_llm_v4.py")
    if not s.exists(): return None
    if "health" in s.read_text().lower() or "ping" in s.read_text().lower():
        return None
    return "multi_llm: нет health check для z-ai"

@critic("C13: local model race condition", "MEDIUM")
def c13(p):
    s = Path("/home/z/my-project/scripts/multi_llm_v4.py")
    if not s.exists(): return None
    c = s.read_text()
    if "Lock" in c or "threading" in c:
        return None
    return "Local model: global без threading.Lock"

@critic("C14: нет graceful shutdown", "LOW")
def c14(p):
    scripts = [Path(f"/home/z/my-project/scripts/{f}") for f in ["multi_llm_v4.py", "truth_gateway.py"]]
    for s in scripts:
        if s.exists():
            c = s.read_text()
            if "atexit" in c or "KeyboardInterrupt" in c:
                return None
    return "Нет graceful shutdown"

@critic("C15: MEMORY.md не обновляется автоматически", "MEDIUM")
def c15(p):
    scripts = Path("/home/z/my-project/scripts")
    for f in scripts.iterdir():
        if f.is_file():
            c = f.read_text(errors='ignore')
            if "MEMORY.md" in c and ("write" in c.lower() or "append" in c.lower()):
                return None
    return "MEMORY.md не обновляется ни одним script"

@critic("C16: §X 'best in world' субъективен", "MEDIUM")
def c16(p):
    sx = p.split("### §X")[1].split("### §XI")[0] if "### §X" in p else ""
    if "измер" in sx.lower() or "metric" in sx.lower():
        return None
    return "§X: нет measurable criteria для 'best in world'"

@critic("C17: TG нет batch processing", "MEDIUM")
def c17(p):
    s = Path("/home/z/my-project/scripts/truth_gateway.py")
    if not s.exists(): return None
    if "batch" in s.read_text().lower():
        return None
    return "TG: нет batch processing"

@critic("C18: no cost tracking", "LOW")
def c18(p):
    scripts = Path("/home/z/my-project/scripts")
    for f in scripts.iterdir():
        if f.is_file():
            c = f.read_text(errors='ignore')
            if "cost" in c.lower() and "token" in c.lower():
                return None
    return "Нет cost tracking"

@critic("C19: §IX нет ML/Data Science домена", "MEDIUM")
def c19(p):
    if "machine learning" in p.lower() or "ML " in p:
        return None
    return "§IX: нет ML/Data Science домена"

@critic("C20: TG annotations ломают markdown", "MEDIUM")
def c20(p):
    sxi = p.split("### §XI")[1].split("### §XII")[0] if "### §XI" in p else ""
    if "escape" in sxi.lower() or "sanitize" in sxi.lower():
        return None
    return "TG: annotations не sanitized для markdown"

@critic("C21: нет log rotation", "LOW")
def c21(p):
    scripts = Path("/home/z/my-project/scripts")
    for f in scripts.iterdir():
        if f.is_file():
            c = f.read_text(errors='ignore')
            if "RotatingFileHandler" in c:
                return None
    return "Нет log rotation"

@critic("C22: §XIII нет cron schedule", "MEDIUM")
def c22(p):
    sxiii = p.split("### §XIII")[1].split("### Порядок")[0] if "### §XIII" in p else ""
    if "cron" in sxiii.lower() or "schedule" in sxiii.lower():
        return None
    return "§XIII: 'раз в неделю' но нет cron"

@critic("C23: IV не различает suggestion vs fact", "MEDIUM")
def c23(p):
    sxii = p.split("### §XII")[1].split("### §XIII")[0] if "### §XII" in p else ""
    if "пользователь предлагает" in sxii.lower():
        return None
    return "IV: не описано когда запускать"

@critic("C24: multi_llm нет exponential backoff для z-ai", "MEDIUM")
def c24(p):
    s = Path("/home/z/my-project/scripts/multi_llm_v4.py")
    if not s.exists(): return None
    c = s.read_text()
    if "exponential" in c.lower() or "2 **" in c or "2 **" in c:
        return None
    return "multi_llm: z-ai retry без exponential backoff"

@critic("C25: TG cache corrupt recovery", "MEDIUM")
def c25(p):
    s = Path("/home/z/my-project/scripts/multi_llm_v4.py")
    if not s.exists(): return None
    c = s.read_text()
    cache_section = c.split("class Cache")[1].split("def get")[0] if "class Cache" in c else ""
    if "try" in cache_section:
        return None
    return "Cache: нет recovery при corrupt"

@critic("C26: §IV нет XML output", "LOW")
def c26(p):
    if "XML" in p:
        return None
    return "§IV: нет правила для XML"

@critic("C27: no concurrent requests", "MEDIUM")
def c27(p):
    s = Path("/home/z/my-project/scripts/multi_llm_v4.py")
    if not s.exists(): return None
    c = s.read_text()
    if "asyncio" in c or "concurrent" in c:
        return None
    return "multi_llm: synchronous, нет concurrent"

@critic("C28: no rollback plan", "MEDIUM")
def c28(p):
    if "rollback" in p.lower() or "откат" in p.lower():
        return None
    return "Нет rollback plan в meta-prompt"

@critic("C29: TG не покрывает законы/регуляции РФ", "MEDIUM")
def c29(p):
    if "НДФЛ" in p or "152-ФЗ" in p:
        return None
    return "TG: нет российских регуляций (152-ФЗ, НДФЛ)"

@critic("C30: IV не покрывает security risks", "HIGH")
def c30(p):
    sxii = p.split("### §XII")[1].split("### §XIII")[0] if "### §XII" in p else ""
    if "security" in sxii.lower() or "уязвим" in sxii.lower():
        return None
    return "IV: не упоминает security risks проверку"

print("=" * 70)
print(f"COMPREHENSIVE CRITIQUE v9.92-FINAL — {len(issues)} critics")
print("=" * 70)

found = []
for name, sev, fn in issues:
    try:
        r = fn(PROMPT)
        if r:
            found.append((name, sev, r))
            icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🔵"}[sev]
            print(f"{icon} {name}")
            print(f"   {r}\n")
    except Exception as e:
        print(f"⚠️ {name}: {e}")

print("=" * 70)
print(f"ИТОГО: {len(found)} проблем")
by_sev = {}
for _, s, _ in found:
    by_sev[s] = by_sev.get(s, 0) + 1
for s in ["HIGH", "MEDIUM", "LOW"]:
    print(f"  {s}: {by_sev.get(s, 0)}")
