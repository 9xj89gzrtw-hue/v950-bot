#!/usr/bin/env python3
"""
Idea Validator — проверяет идеи пользователя через research перед внедрением.

Принцип: пользователь может предложить идею, которая:
1. Уже устарела (вышла новая альтернатива)
2. Не работает в реальности
3. Может ухудшить результат

Validator:
1. Принимает идею (текст)
2. Ищет через web_search актуальные данные про эту идею
3. Проверяет: есть ли более новые альтернативы?
4. Проверяет: подтверждается ли что идея работает?
5. Возвращает verdict: IMPLEMENT / RESEARCH_MORE / AVOID / ALTERNATIVE_FOUND
"""
import json
import subprocess
import os
import sys
import time
import re
from typing import List, Dict
from pathlib import Path

sys.path.insert(0, '/home/z/my-project/scripts')


def web_search(query: str, num: int = 5) -> List[Dict]:
    """Multi-source web search."""
    # z-ai first
    try:
        tmp_out = f"/tmp/_search_{os.getpid()}_{int(time.time()*1000) % 1000000}.json"
        cmd = ["z-ai", "function", "-n", "web_search",
               "-a", json.dumps({"query": query, "num": num}),
               "-o", tmp_out]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
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
        resp = urllib.request.urlopen(req, timeout=15)
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


def validate_idea(idea: str, context: str = "") -> Dict:
    """
    Validate user idea through web research.
    
    Returns:
    {
        'idea': str,
        'verdict': 'IMPLEMENT' | 'RESEARCH_MORE' | 'AVOID' | 'ALTERNATIVE_FOUND',
        'confidence': float 0-1,
        'evidence': List[Dict],
        'alternatives': List[str],
        'risks': List[str],
        'recommendation': str,
        'research_date': str
    }
    """
    research_date = time.strftime('%Y-%m-%d')
    
    print(f"[idea_validator] Researching: '{idea[:80]}'...")
    
    # Search 1: Direct idea query
    print(f"  → Searching for idea viability...")
    direct_results = web_search(f"{idea} 2026 review viability", num=5)
    
    # Search 2: Alternatives
    print(f"  → Searching for alternatives...")
    alt_results = web_search(f"alternatives to {idea} 2026", num=5)
    
    # Search 3: Latest version/release
    print(f"  → Searching for latest releases...")
    # Extract potential version numbers / model names
    model_names = re.findall(r'\b(GPT-\d+|GLM-\d+|Claude\s+\d+|Llama\s+\d+|Qwen[\d.]+|Gemma\s+\d+|Next\.js\s+\d+|React\s+\d+)\b', idea, re.IGNORECASE)
    if model_names:
        latest_results = web_search(f"latest {model_names[0]} 2026 release", num=3)
    else:
        latest_results = []
    
    all_results = direct_results + alt_results + latest_results
    
    # Analyze
    evidence = []
    alternatives = []
    risks = []
    
    for r in all_results[:10]:
        snippet = r.get('snippet', '').lower()
        name = r.get('name', '').lower()
        
        # Check for "deprecated" / "outdated" / "obsolete"
        if any(w in snippet for w in ['deprecated', 'outdated', 'obsolete', 'no longer', 'discontinued']):
            risks.append(f"Outdated: {r.get('name','')} - {snippet[:100]}")
        
        # Check for "better than" / "alternative" / "replaces"
        if any(w in snippet for w in ['better than', 'alternative', 'replaces', 'superior', 'upgrade']):
            alternatives.append(f"{r.get('name','')}: {snippet[:150]}")
        
        # Check for "2026" mentions (recent)
        if '2026' in snippet:
            evidence.append(f"Recent: {r.get('name','')} ({r.get('date','')}) - {snippet[:100]}")
        
        # Check for "vulnerable" / "security issue" / "breach"
        if any(w in snippet for w in ['vulnerab', 'security', 'breach', 'exploit', 'cve-']):
            risks.append(f"Security: {r.get('name','')} - {snippet[:100]}")
    
    # Determine verdict
    if risks and not alternatives:
        verdict = "AVOID"
        confidence = 0.8
        recommendation = f"Idea may be outdated or risky. Risks found: {len(risks)}. Research alternatives."
    elif alternatives and len(alternatives) > 2:
        verdict = "ALTERNATIVE_FOUND"
        confidence = 0.7
        recommendation = f"Found {len(alternatives)} newer alternatives. Consider these instead."
    elif evidence and len(evidence) >= 2:
        verdict = "IMPLEMENT"
        confidence = 0.6
        recommendation = "Idea appears current with recent evidence. Proceed with implementation."
    elif not all_results:
        verdict = "RESEARCH_MORE"
        confidence = 0.3
        recommendation = "No search results found. Cannot verify. Research manually before implementing."
    else:
        verdict = "RESEARCH_MORE"
        confidence = 0.5
        recommendation = "Mixed signals. Research more before implementing."
    
    return {
        'idea': idea,
        'verdict': verdict,
        'confidence': confidence,
        'evidence': evidence[:5],
        'alternatives': alternatives[:5],
        'risks': risks[:3],
        'recommendation': recommendation,
        'research_date': research_date,
        'total_sources_checked': len(all_results),
    }


if __name__ == "__main__":
    # Test with user's idea
    test_ideas = [
        "Use Qwen3-4B as the latest model for our system",
        "Implement Pollinations as primary LLM provider",
        "Use Python 3.10 for the project",
    ]
    
    for idea in test_ideas:
        print(f"\n{'='*70}")
        result = validate_idea(idea)
        print(f"\nVerdict: {result['verdict']} (confidence: {result['confidence']})")
        print(f"Recommendation: {result['recommendation']}")
        if result['risks']:
            print(f"Risks:")
            for r in result['risks']:
                print(f"  ⚠️ {r}")
        if result['alternatives']:
            print(f"Alternatives:")
            for a in result['alternatives']:
                print(f"  💡 {a}")
        if result['evidence']:
            print(f"Evidence:")
            for e in result['evidence']:
                print(f"  ✓ {e}")
