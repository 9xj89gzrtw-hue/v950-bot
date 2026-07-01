#!/usr/bin/env python3
"""
Output Validator — автоматическая проверка OUTPUT на длину, placeholders, vagueness.
Вызывается после генерации OUTPUT для §X "best-in-world" задач.
"""
import re
from typing import Dict, List

DOMAIN_MIN_WORDS = {
    "web": 1500,
    "invest": 1200,
    "aimoney": 1500,
    "default": 800,
}

PLACEHOLDER_PATTERNS = [
    r"//\s*TODO",
    r"//\s*FIXME",
    r"//\s*implement here",
    r"//\s*add your",
    r"<your[^>]+>",
    r"\[your[^\]]+\]",
    r"placeholder",
    r"coming soon",
    r"to be implemented",
]

VAGUE_PATTERNS = [
    r"\bconsider\s+\w+",
    r"\byou might\b",
    r"\byou could\b",
    r"\bperhaps\b",
    r"\bmaybe\b",
    r"\bsome\s+\w+",
    r"\bseveral\s+\w+",
]


def detect_domain(text: str) -> str:
    """Detect domain from OUTPUT content."""
    lower = text.lower()
    if any(w in lower for w in ["next.js", "react", "tailwind", "css", "html", "component", "deploy", "vercel"]):
        return "web"
    if any(w in lower for w in ["portfolio", "stock", "ticker", "buy", "sell", "var", "sharpe", "sec rule", "finra"]):
        return "invest"
    if any(w in lower for w in ["saas", "mrr", "freelance", "youtube", "monetiz", "income", "client"]):
        return "aimoney"
    return "default"


def count_words(text: str) -> int:
    """Count words in text."""
    # Remove code blocks for counting (code is verbose but not "content")
    no_code = re.sub(r"```[\s\S]*?```", "", text)
    return len(no_code.split())


def find_placeholders(text: str) -> List[str]:
    """Find placeholder patterns."""
    found = []
    for pattern in PLACEHOLDER_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            # Get context
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            context = text[start:end].replace("\n", " ").strip()
            found.append(f"'{match.group()}' in: ...{context}...")
    return found[:5]  # max 5


def find_vague(text: str) -> List[str]:
    """Find vague language patterns."""
    found = []
    for pattern in VAGUE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, match.start() - 10)
            end = min(len(text), match.end() + 30)
            context = text[start:end].replace("\n", " ").strip()
            found.append(f"'{match.group()}' in: ...{context}...")
    return found[:5]


def validate_output(text: str, domain: str = None) -> Dict:
    """Validate OUTPUT for quality."""
    if not domain:
        domain = detect_domain(text)
    
    min_words = DOMAIN_MIN_WORDS.get(domain, 800)
    word_count = count_words(text)
    placeholders = find_placeholders(text)
    vague = find_vague(text)
    
    issues = []
    
    if word_count < min_words:
        issues.append(f"[TOO_SHORT: {word_count} words, need {min_words} for {domain}]")
    
    if placeholders:
        issues.append(f"[PLACEHOLDER_FOUND: {len(placeholders)} placeholders]")
        for p in placeholders[:2]:
            issues.append(f"  - {p}")
    
    if vague:
        issues.append(f"[VAGUE: {len(vague)} vague phrases]")
        for v in vague[:2]:
            issues.append(f"  - {v}")
    
    return {
        "domain": domain,
        "word_count": word_count,
        "min_required": min_words,
        "placeholders": placeholders,
        "vague_phrases": vague,
        "issues": issues,
        "passed": len(issues) == 0,
    }


if __name__ == "__main__":
    # Test
    short_output = "Use Next.js for the site. Consider adding Tailwind. // TODO: implement components"
    long_output = """# SaaS Landing Page
    
## Quick Start
Run `npx create-next-app@14` to create the project.
Install dependencies: `npm install lucide-react @radix-ui/react-slot`

## Hero Component
```tsx
import { Button } from '@/components/ui/button';

export function Hero() {
  return (
    <section className="py-20">
      <h1 className="text-5xl">Build Better Products</h1>
      <Button>Get Started</Button>
    </section>
  );
}
```
""" + " word " * 500  # padding to reach 1500 words
    
    print("=== Short output test ===")
    r = validate_output(short_output)
    print(f"Domain: {r['domain']}, Words: {r['word_count']}/{r['min_required']}")
    print(f"Passed: {r['passed']}")
    for issue in r['issues']:
        print(f"  {issue}")
    
    print("\n=== Long output test ===")
    r = validate_output(long_output)
    print(f"Domain: {r['domain']}, Words: {r['word_count']}/{r['min_required']}")
    print(f"Passed: {r['passed']}")
    for issue in r['issues']:
        print(f"  {issue}")
