#!/usr/bin/env python3
"""
CoT Enforcer — проверяет что OUTPUT содержит reasoning steps + final answer.
"""
import re
from typing import Dict


REASONING_KEYWORDS = [
    'calculate', 'посчитай', 'analyze', 'проанализируй',
    'plan', 'спланируй', 'why', 'почему', 'how', 'как',
    'compare', 'сравни', 'evaluate', 'оцени',
    'step', 'шаг', 'reasoning', 'размышлени',
]


def needs_cot(user_prompt: str) -> bool:
    """Check if task requires chain-of-thought."""
    lower = user_prompt.lower()
    return any(kw in lower for kw in REASONING_KEYWORDS)


def check_cot_compliance(output: str) -> Dict:
    """Check if OUTPUT has CoT structure: steps + answer."""
    issues = []
    
    # Check for steps
    has_steps = bool(re.search(r'(?:step|шаг)\s*\d', output, re.IGNORECASE))
    if not has_steps:
        # Also check for numbered reasoning
        has_numbered = bool(re.search(r'^\d+\.\s+\w+', output, re.MULTILINE))
        if not has_numbered:
            issues.append("[COT_MISSING_STEPS: no 'Step N' or numbered reasoning found]")
    
    # Check for final answer
    has_answer = bool(re.search(r'(?:answer|ответ|итог|result|результат)\s*[:=]', output, re.IGNORECASE))
    if not has_answer:
        # Check for bold final
        has_bold = bool(re.search(r'\*\*[^*]{5,100}\*\*\s*$', output.strip()))
        if not has_bold:
            issues.append("[COT_MISSING_ANSWER: no 'Answer:' or '**final**' found]")
    
    return {
        'compliant': len(issues) == 0,
        'has_steps': has_steps,
        'has_answer': has_answer,
        'issues': issues,
    }


def enforce_cot(system_prompt: str, user_prompt: str) -> str:
    """Augment system prompt with CoT requirement if task needs it."""
    if not needs_cot(user_prompt):
        return system_prompt
    
    cot_addition = """

CHAIN-OF-THOUGHT REQUIRED for this task. Structure your response:

**Reasoning:**
Step 1: [first step]
Step 2: [second step]
...

**Answer:** [final answer]

End your response with '**Answer:** [value]'."""
    
    return system_prompt + cot_addition


if __name__ == "__main__":
    # Test
    test_outputs = [
        # Good CoT
        """**Reasoning:**
Step 1: cost = 200 × $150 = $30,000
Step 2: value = 200 × $180 = $36,000
Step 3: gain = $36,000 - $30,000 = $6,000
Step 4: % = $6,000/$30,000 = 20%

**Answer:** 20% return""",
        
        # Missing steps
        "The return is 20%. Answer: 20%",
        
        # Missing answer
        """Step 1: cost = $30,000
Step 2: value = $36,000
Step 3: gain = $6,000""",
        
        # Missing both
        "The return is about 17%.",
    ]
    
    for i, out in enumerate(test_outputs):
        result = check_cot_compliance(out)
        print(f"Test {i+1}: compliant={result['compliant']}, steps={result['has_steps']}, answer={result['has_answer']}")
        if result['issues']:
            for issue in result['issues']:
                print(f"  {issue}")
        print()
    
    # Test needs_cot
    prompts = [
        "Calculate 17 * 23",
        "What is the capital of France?",
        "Analyze this portfolio",
        "Tell me a joke",
        "Plan the project timeline",
    ]
    print("=== needs_cot tests ===")
    for p in prompts:
        print(f"  '{p}': {needs_cot(p)}")
