#!/usr/bin/env python3
"""
Truth Gateway — структурная защита от вранья.

Принцип: правило в промпте = пожелание. Парсер = enforcement.

Работа:
1. Принимает OUTPUT от LLM
2. Извлекает factual claims (версии ПО, цены, даты, числа, имена)
3. Для каждого claim вызывает web_search
4. Если claim не подтверждается → помечает [UNVERIFIED]
5. Возвращает verified OUTPUT + список проверок
"""
import json
import re
import sys
import os
import subprocess
import time
from pathlib import Path
from typing import List, Dict


# Eternal facts (не требуют проверки)
ETERNAL_PATTERNS = [
    r'\b[0-9]+\s*[+\-*/]\s*[0-9]+\s*=\s*[0-9]+\b',
    r'\bπ\s*=\s*3\.14',
    r'\b(19[0-9][0-9])\b',  # years before 2000
    r'\b(World War II|WW2|Вторая мировая)\b',
]

# Changing facts patterns (требуют проверки)
CHANGING_PATTERNS = {
    'model_versions': r'\b(GPT-[0-9]+|GLM-[0-9]+|Claude\s+[0-9]+|Llama\s+[0-9]+|Qwen[0-9]?\.?[0-9]?-?[0-9]+[A-Z]?|Gemini\s+[0-9])\b',
    'software_versions': r'\b(Next\.js|React|Vue|Python|Node\.js|Tailwind|Postgres|MongoDB)\s+v?(\d+\.?\d*)\b',
    'prices': r'\$(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:USD|per|/share|/month|/user)?',
    'percentages': r'(\d+(?:\.\d+)?)\s*%',
    'dates_future': r'\b(20[2-9][0-9])\b',
    'crypto_tickers': r'\b(BTC|ETH|SOL|USDT|BNB|XRP|ADA|DOT)\b',
    'stock_tickers': r'\b(AAPL|MSFT|NVDA|GOOGL|TSLA|META|AMZN|NFLX)\b',
    'company_names': r'\b(OpenAI|Anthropic|Zhipu|DeepSeek|Mistral)\b',
    'api_names': r'\b(Stripe API|OpenAI API|Yahoo Finance|Bloomberg|CoinGecko)\b',
}


def is_eternal(text: str) -> bool:
    for pattern in ETERNAL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def extract_claims(text: str) -> List[Dict]:
    claims = []
    for category, pattern in CHANGING_PATTERNS.items():
        for match in re.finditer(pattern, text, re.IGNORECASE):
            claim_text = match.group(0)
            start = max(0, match.start() - 50)
            context = text[start:match.end() + 50]
            if is_eternal(context):
                continue
            claims.append({
                'category': category,
                'text': claim_text,
                'context': context,
                'position': match.start(),
            })
    
    seen = set()
    unique = []
    for c in claims:
        if c['text'].lower() not in seen:
            seen.add(c['text'].lower())
            unique.append(c)
    return unique


def web_search(query: str, num: int = 3) -> List[Dict]:
    """Multi-source web search: z-ai → Wikipedia API → DuckDuckGo."""
    # Source 1: z-ai (may be rate-limited)
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
    
    # Source 2: Wikipedia API (always works, no auth)
    try:
        import urllib.request
        encoded = urllib.parse.quote(query)
        url = f'https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded}&format=json&srlimit={num}'
        req = urllib.request.Request(url, headers={'User-Agent': 'TruthGateway/1.0'})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        results = []
        for r in data.get('query', {}).get('search', [])[:num]:
            results.append({
                'name': r.get('title', ''),
                'snippet': r.get('snippet', '')[:300],
                'url': f'https://en.wikipedia.org/wiki/{r.get("title","").replace(" ","_")}',
                'host_name': 'en.wikipedia.org',
            })
        if results:
            return results
    except Exception:
        pass
    
    # Source 3: DuckDuckGo API
    try:
        import urllib.request, urllib.parse
        encoded = urllib.parse.quote(query)
        url = f'https://api.duckduckgo.com/?q={encoded}&format=json&no_redirect=1'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        results = []
        if data.get('AbstractText'):
            results.append({
                'name': data.get('Heading', query),
                'snippet': data.get('AbstractText', ''),
                'url': data.get('AbstractURL', ''),
                'host_name': 'duckduckgo.com',
            })
        for t in data.get('RelatedTopics', [])[:num-1]:
            if isinstance(t, dict) and t.get('Text'):
                results.append({
                    'name': t.get('Text', '')[:80],
                    'snippet': t.get('Text', ''),
                    'url': t.get('FirstURL', ''),
                    'host_name': 'duckduckgo.com',
                })
        return results[:num]
    except Exception:
        pass
    
    return []


def verify_claim(claim: Dict) -> Dict:
    query = f"{claim['text']} {claim['category']} latest 2025"
    results = web_search(query, num=3)
    
    if not results:
        return {**claim, 'verified': False, 'reason': 'no_search_results', 'sources': []}
    
    claim_lower = claim['text'].lower()
    for r in results:
        snippet = (r.get('snippet') or '').lower()
        name = (r.get('name') or '').lower()
        if claim['category'] == 'model_versions':
            version_match = re.search(r'(\d+\.?\d*)', claim['text'])
            if version_match:
                version = version_match.group(1)
                if version in snippet or version in name:
                    return {**claim, 'verified': True, 'sources': [r.get('url', '')]}
        elif claim_lower in snippet or claim_lower in name:
            return {**claim, 'verified': True, 'sources': [r.get('url', '')]}
    
    return {**claim, 'verified': False, 'reason': 'not_found_in_results',
            'sources': [r.get('url', '') for r in results]}


def annotate_output(text: str, claims: List[Dict]) -> str:
    annotated = text
    sorted_claims = sorted(claims, key=lambda c: c.get('position', 0), reverse=True)
    for c in sorted_claims:
        if c.get('verified') is True:
            sources = c.get('sources', [''])[:1]
            src = sources[0] if sources else ''
            tag = f" [VERIFIED" + (f": {src[:50]}" if src else "") + "]"
        elif c.get('verified') is False:
            tag = f" [UNVERIFIED: needs manual check]"
        else:
            tag = ""
        
        if tag:
            pos = c['position'] + len(c['text'])
            annotated = annotated[:pos] + tag + annotated[pos:]
    
    return annotated


def truth_gateway(output: str, verify: bool = True, max_claims: int = 10) -> Dict:
    print(f"[truth_gateway] Analyzing {len(output)} chars...")
    claims = extract_claims(output)
    print(f"[truth_gateway] Found {len(claims)} unique claims")
    
    if not verify:
        return {
            'original': output,
            'annotated': output,
            'claims': claims,
            'stats': {'total': len(claims), 'verified': 0, 'unverified': 0, 'skipped': len(claims)},
            'summary': f"Skipping verification. Found {len(claims)} potential claims."
        }
    
    verified_count = 0
    unverified_count = 0
    skipped = 0
    
    for i, claim in enumerate(claims):
        if i >= max_claims:
            print(f"  [{i+1}/{len(claims)}] {claim['category']}: '{claim['text'][:50]}' SKIP (max reached)")
            claim['verified'] = None
            claim['reason'] = 'max_claims_reached'
            skipped += 1
            continue
        
        print(f"  [{i+1}/{min(len(claims),max_claims)}] {claim['category']}: '{claim['text'][:50]}'...", end='', flush=True)
        result = verify_claim(claim)
        claim.update(result)
        
        if result.get('verified'):
            print(" ✓")
            verified_count += 1
        else:
            print(f" ✗ ({result.get('reason', 'unknown')[:30]})")
            unverified_count += 1
        
        time.sleep(1.5)  # avoid rate limit
    
    annotated = annotate_output(output, claims)
    summary = f"Verified {verified_count}/{verified_count + unverified_count} claims ({skipped} skipped)."
    if unverified_count > 0:
        summary += f" ⚠️ {unverified_count} claims need manual verification."
    
    return {
        'original': output,
        'annotated': annotated,
        'claims': claims,
        'stats': {'total': len(claims), 'verified': verified_count, 'unverified': unverified_count, 'skipped': skipped},
        'summary': summary
    }


if __name__ == "__main__":
    test = """
    GPT-5 from OpenAI is the most capable model in 2025.
    GLM-5 from Zhipu is the leading Chinese model.
    Claude 4 from Anthropic excels at reasoning.
    NVDA stock at $180.
    Next.js 14 with Tailwind 3.4.
    """
    print("=" * 70)
    print("TRUTH GATEWAY TEST")
    print("=" * 70)
    print(f"INPUT:\n{test}\n")
    
    result = truth_gateway(test, verify=False)
    print(f"\nClaims found: {len(result['claims'])}")
    for c in result['claims']:
        print(f"  [{c['category']}] {c['text']}")
    print(f"\n{result['summary']}")
