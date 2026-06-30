#!/usr/bin/env python3
"""
Idea Validator v2 — с timeout, cache, AVOID protocol.
"""
import json
import subprocess
import os
import sys
import time
import re
import hashlib
from typing import List, Dict
from pathlib import Path

sys.path.insert(0, '/home/z/my-project/scripts')

CACHE_FILE = Path("/home/z/my-project/download/_idea_validator_cache.json")


def load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except:
            return {}
    return {}


def save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def web_search(query: str, num: int = 5, timeout: int = 15) -> List[Dict]:
    """Multi-source web search with timeout."""
    # z-ai first
    try:
        tmp_out = f"/tmp/_search_{os.getpid()}_{int(time.time()*1000) % 1000000}.json"
        cmd = ["z-ai", "function", "-n", "web_search",
               "-a", json.dumps({"query": query, "num": num}),
               "-o", tmp_out]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0 and os.path.exists(tmp_out):
            data = json.loads(Path(tmp_out).read_text())
            os.unlink(tmp_out)
            if isinstance(data, list) and data:
                return data[:num]
        if os.path.exists(tmp_out):
            os.unlink(tmp_out)
    except Exception:
        pass

    # Wikipedia fallback
    try:
        import urllib.request, urllib.parse
        encoded = urllib.parse.quote(query)
        url = f'https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded}&format=json&srlimit={num}'
        req = urllib.request.Request(url, headers={'User-Agent': 'IdeaValidator/1.0'})
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read())
        results = []
        for r in data.get('query', {}).get('search', [])[:num]:
            results.append({
                'name': r.get('title', ''),
                'snippet': r.get('snippet', '')[:300],
                'url': f'https://en.wikipedia.org/wiki/{r.get("title","").replace(" ","_")}',
                'host_name': 'en.wikipedia.org',
                'date': r.get('timestamp', '')[:10],
            })
        if results:
            return results
    except Exception:
        pass

    return []


def validate_idea(idea: str, context: str = "", use_cache: bool = True) -> Dict:
    """Validate user idea with timeout, cache, security check."""
    research_date = time.strftime('%Y-%m-%d')

    # Cache check
    cache = load_cache() if use_cache else {}
    cache_key = hashlib.sha256(idea.encode()).hexdigest()[:16]
    if cache_key in cache:
        cached = cache[cache_key]
        # Cache valid for 7 days
        cache_date = cached.get('research_date', '')
        if cache_date and (time.time() - time.mktime(time.strptime(cache_date, '%Y-%m-%d'))) < 7 * 86400:
            print(f"[idea_validator] CACHE HIT")
            return cached

    print(f"[idea_validator] Researching: '{idea[:80]}'...")

    # Search 1: Direct
    direct = web_search(f"{idea} 2026 review viability", num=5, timeout=15)
    # Search 2: Alternatives
    alt = web_search(f"alternatives to {idea} 2026", num=5, timeout=15)
    # Search 3: Latest version
    model_names = re.findall(r'\b(GPT-\d+|GLM-\d+|Claude\s+\d+|Llama\s+\d+|Qwen[\d.]+|Gemma\s+\d+|Next\.js\s+\d+)\b', idea, re.IGNORECASE)
    latest = web_search(f"latest {model_names[0]} 2026 release", num=3, timeout=15) if model_names else []
    # Search 4: Security
    security = web_search(f"{idea} vulnerability security issue 2026", num=3, timeout=15)

    all_results = direct + alt + latest + security

    evidence = []
    alternatives = []
    risks = []
    security_risks = []

    for r in all_results[:15]:
        snippet = (r.get('snippet', '') or '').lower()
        name = (r.get('name', '') or '').lower()

        if any(w in snippet for w in ['deprecated', 'outdated', 'obsolete', 'no longer', 'discontinued']):
            risks.append(f"Outdated: {r.get('name','')}")
        if any(w in snippet for w in ['better than', 'alternative', 'replaces', 'superior', 'upgrade']):
            alternatives.append(f"{r.get('name','')}: {snippet[:100]}")
        if '2026' in snippet:
            evidence.append(f"Recent: {r.get('name','')}")
        if any(w in snippet for w in ['vulnerab', 'security', 'breach', 'exploit', 'cve-']):
            security_risks.append(f"Security: {r.get('name','')} - {snippet[:80]}")

    # Verdict
    if security_risks and not alternatives:
        verdict = "AVOID"
        confidence = 0.85
        recommendation = f"Security risks found: {len(security_risks)}. Do not implement without mitigation."
    elif risks and not alternatives:
        verdict = "AVOID"
        confidence = 0.8
        recommendation = f"Idea may be outdated. Risks: {len(risks)}. Research alternatives."
    elif alternatives and len(alternatives) > 2:
        verdict = "ALTERNATIVE_FOUND"
        confidence = 0.7
        recommendation = f"Found {len(alternatives)} newer alternatives. Consider these."
    elif evidence and len(evidence) >= 2:
        verdict = "IMPLEMENT"
        confidence = 0.6
        recommendation = "Idea appears current. Proceed."
    elif not all_results:
        verdict = "RESEARCH_MORE"
        confidence = 0.3
        recommendation = "No results. Research manually."
    else:
        verdict = "RESEARCH_MORE"
        confidence = 0.5
        recommendation = "Mixed signals. Research more."

    result = {
        'idea': idea,
        'verdict': verdict,
        'confidence': confidence,
        'evidence': evidence[:5],
        'alternatives': alternatives[:5],
        'risks': risks[:3],
        'security_risks': security_risks[:3],
        'recommendation': recommendation,
        'research_date': research_date,
        'total_sources_checked': len(all_results),
    }

    # Cache result
    if use_cache:
        cache[cache_key] = result
        save_cache(cache)

    return result


def handle_user_insists(idea: str, validation: dict) -> dict:
    """Protocol when user insists on AVOID idea."""
    if validation['verdict'] != 'AVOID':
        return validation

    return {
        **validation,
        'insists_protocol': {
            'step_1': 'Объясни риски ещё раз с конкретными source citations',
            'step_2': 'Предложи безопасную альтернативу из alternatives list',
            'step_3': 'Если user всё равно настаивает — требуй явное подтверждение: "Я понимаю риски [X], реализуй всё равно (yes/no)"',
            'step_4': 'Только после "yes" — внедряй с пометкой [USER-ACCEPTED-RISK]',
            'step_5': 'Логируй в MEMORY.md под "user_accepted_risks"',
        }
    }


if __name__ == "__main__":
    test = "Use Qwen3-4B as primary model"
    r = validate_idea(test)
    print(f"\nVerdict: {r['verdict']} (confidence: {r['confidence']})")
    print(f"Sources: {r['total_sources_checked']}")
    if r['risks']:
        print("Risks:", r['risks'])
    if r['alternatives']:
        print("Alternatives:", r['alternatives'])
