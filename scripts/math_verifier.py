#!/usr/bin/env python3
"""
Math Verifier — проверяет математические расчёты в OUTPUT.
Извлекает формулы вида "X * Y = Z" и проверяет их.
"""
import re
from typing import List, Dict


def extract_calculations(text: str) -> List[Dict]:
    """Извлекает математические расчёты из текста."""
    calcs = []
    
    # Pattern: "X * Y = Z" or "X × Y = Z" or "X times Y"
    patterns = [
        # "200 × $150 = $30,000" or "200 * 150 = 30000"
        r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*[×*x]\s*\$?(\d+(?:,\d{3})*(?:\.\d+)?)\s*=\s*\$?(\d+(?:,\d{3})*(?:\.\d+)?)',
        # "X% of Y = Z"
        r'(\d+(?:\.\d+)?)\s*%\s*of\s*\$?(\d+(?:,\d{3})*(?:\.\d+)?)\s*=\s*\$?(\d+(?:,\d{3})*(?:\.\d+)?)',
        # "X% tax on Y" (no =, compute expected)
        r'(\d+(?:\.\d+)?)\s*%\s*(?:tax|rate)\s*on\s*\$?(\d+(?:,\d{3})*(?:\.\d+)?)',
        # "gain of $X" or "profit of $X"
        r'(?:gain|profit|loss)\s*of\s*\$(\d+(?:,\d{3})*(?:\.\d+)?)',
        # "X% return" or "X% gain"
        r'(\d+(?:\.\d+)?)\s*%\s*(?:return|gain|loss|ROI)',
    ]
    
    for i, pattern in enumerate(patterns):
        for match in re.finditer(pattern, text, re.IGNORECASE):
            groups = match.groups()
            calc = {
                'pattern_type': i,
                'original': match.group(0),
                'position': match.start(),
            }
            if i == 0:  # X * Y = Z
                x = float(groups[0].replace(',', ''))
                y = float(groups[1].replace(',', ''))
                z = float(groups[2].replace(',', ''))
                calc['expected'] = x * y
                calc['actual'] = z
                calc['valid'] = abs(calc['expected'] - calc['actual']) < 0.01 * max(calc['expected'], 1)
            elif i == 1:  # X% of Y = Z
                pct = float(groups[0])
                y = float(groups[1].replace(',', ''))
                z = float(groups[2].replace(',', ''))
                calc['expected'] = y * pct / 100
                calc['actual'] = z
                calc['valid'] = abs(calc['expected'] - calc['actual']) < 0.01 * max(calc['expected'], 1)
            elif i == 2:  # X% tax on Y (compute expected, no = in text)
                pct = float(groups[0])
                y = float(groups[1].replace(',', ''))
                calc['expected'] = y * pct / 100
                calc['actual'] = None  # not stated
                calc['valid'] = None
            calcs.append(calc)
    
    return calcs


def verify_calculation(context: str, claimed_value: float, value_type: str, **kwargs) -> Dict:
    """Verify a specific calculation given context."""
    result = {'claimed': claimed_value, 'valid': False, 'reason': ''}
    
    if value_type == 'gain':
        cost = kwargs.get('cost')
        current = kwargs.get('current')
        if cost and current:
            expected = current - cost
            result['expected'] = expected
            result['valid'] = abs(expected - claimed_value) < 0.01 * max(expected, 1)
            if not result['valid']:
                result['reason'] = f'Expected {expected}, got {claimed_value}'
    elif value_type == 'percentage':
        cost = kwargs.get('cost')
        gain = kwargs.get('gain')
        if cost and gain:
            expected_pct = (gain / cost) * 100
            result['expected'] = expected_pct
            result['valid'] = abs(expected_pct - claimed_value) < 0.5  # 0.5% tolerance
            if not result['valid']:
                result['reason'] = f'Expected {expected_pct:.1f}%, got {claimed_value}%'
    elif value_type == 'tax':
        gain = kwargs.get('gain')
        rate = kwargs.get('rate')
        if gain and rate:
            expected_tax = gain * rate / 100
            result['expected'] = expected_tax
            result['valid'] = abs(expected_tax - claimed_value) < 0.01 * max(expected_tax, 1)
            if not result['valid']:
                result['reason'] = f'Expected {expected_tax}, got {claimed_value}'
    
    return result


def extract_financial_claims(text: str) -> List[Dict]:
    """Extract financial claims that can be verified."""
    claims = []
    
    # Pattern: "total cost is $X" / "total value is $X" / "net gain of $X" / "$X gain" / "$X cost"
    for match in re.finditer(r'(?:total\s+)?(?:cost|value|gain|profit|loss|tax)\s+(?:is|of|amounts? to)?\s*\$(\d+(?:,\d{3})*(?:\.\d+)?)', text, re.IGNORECASE):
        context_start = max(0, match.start() - 20)
        context = text[context_start:match.start()]
        label = re.search(r'(cost|value|gain|profit|loss|tax)', match.group(0), re.IGNORECASE).group(1).lower()
        if 'net' in context.lower():
            label = 'net_gain'
        claims.append({
            'type': 'financial_value',
            'label': label,
            'value': float(match.group(1).replace(',', '')),
            'original': match.group(0),
            'position': match.start(),
        })
    
    # Pattern: "$X total" / "$X gain" / "$X cost" (value before label)
    for match in re.finditer(r'\$(\d+(?:,\d{3})*(?:\.\d+)?)\s+(total|cost|value|gain|profit|loss|tax)', text, re.IGNORECASE):
        label = match.group(2).lower()
        context_start = max(0, match.start() - 20)
        context = text[context_start:match.start()]
        if 'net' in context.lower():
            label = 'net_gain'
        # Don't duplicate if already found
        if not any(c['type'] == 'financial_value' and c['value'] == float(match.group(1).replace(',','')) for c in claims):
            claims.append({
                'type': 'financial_value',
                'label': label,
                'value': float(match.group(1).replace(',', '')),
                'original': match.group(0),
                'position': match.start(),
            })
    
    # Pattern: "X% return" / "X% gain" / "return is X%" / "ROI of X%" / "return on investment is X%"
    for match in re.finditer(r'(\d+(?:\.\d+)?)\s*%', text):
        pct = float(match.group(1))
        # Get context to determine label
        start = max(0, match.start() - 40)
        context = text[start:match.start() + 10].lower()
        label = None
        for l in ['return on investment', 'roi', 'return', 'gain', 'loss', 'tax', 'rate']:
            if l in context:
                label = l.replace('return on investment', 'return')
                break
        if label:
            claims.append({
                'type': 'percentage',
                'label': label,
                'value': pct,
                'original': match.group(0),
                'position': match.start(),
            })
    
    # Pattern: "X shares at $Y" / "X shares of TICKER at $Y"
    for match in re.finditer(r'(\d+)\s+shares?\s+(?:of\s+\w+\s+)?(?:at|@|bought at|priced at)\s*\$(\d+(?:,\d{3})*(?:\.\d+)?)', text, re.IGNORECASE):
        claims.append({
            'type': 'position',
            'shares': int(match.group(1)),
            'price': float(match.group(2).replace(',', '')),
            'original': match.group(0),
            'position': match.start(),
        })
    
    # Pattern: "current price $X" / "currently $X" / "valued at $X"
    for match in re.finditer(r'(?:current(?:ly)?\s+(?:price|valued)?|valued at|now at)\s*\$(\d+(?:,\d{3})*(?:\.\d+)?)', text, re.IGNORECASE):
        claims.append({
            'type': 'current_price',
            'value': float(match.group(1).replace(',', '')),
            'original': match.group(0),
            'position': match.start(),
        })
    
    return claims


def verify_financial_consistency(claims: List[Dict]) -> List[Dict]:
    """Verify financial claims are mathematically consistent."""
    issues = []
    
    # Find position + current price
    positions = [c for c in claims if c['type'] == 'position']
    current_prices = [c for c in claims if c['type'] == 'current_price']
    financials = {c['label']: c['value'] for c in claims if c['type'] == 'financial_value'}
    percentages = {c['label']: c['value'] for c in claims if c['type'] == 'percentage'}
    
    if positions and current_prices:
        pos = positions[0]
        cur = current_prices[0]
        expected_cost = pos['shares'] * pos['price']
        expected_value = pos['shares'] * cur['value']
        expected_gain = expected_value - expected_cost
        expected_pct = (expected_gain / expected_cost) * 100 if expected_cost else 0
        
        # Check total cost
        if 'cost' in financials:
            actual = financials['cost']
            if abs(actual - expected_cost) > 1:
                issues.append({
                    'issue': 'COST_MISMATCH',
                    'expected': expected_cost,
                    'actual': actual,
                    'message': f"Cost should be {pos['shares']} × ${pos['price']} = ${expected_cost:,.0f}, but stated as ${actual:,.0f}"
                })
        
        # Check total value
        if 'value' in financials:
            actual = financials['value']
            if abs(actual - expected_value) > 1:
                issues.append({
                    'issue': 'VALUE_MISMATCH',
                    'expected': expected_value,
                    'actual': actual,
                    'message': f"Value should be {pos['shares']} × ${cur['value']} = ${expected_value:,.0f}, but stated as ${actual:,.0f}"
                })
        
        # Check gain
        if 'gain' in financials:
            actual = financials['gain']
            if abs(actual - expected_gain) > 1:
                issues.append({
                    'issue': 'GAIN_MISMATCH',
                    'expected': expected_gain,
                    'actual': actual,
                    'message': f"Gain should be ${expected_value:,.0f} - ${expected_cost:,.0f} = ${expected_gain:,.0f}, but stated as ${actual:,.0f}"
                })
        
        # Check percentage
        for label in ['return', 'gain', 'roi']:
            if label in percentages:
                actual = percentages[label]
                if abs(actual - expected_pct) > 0.5:
                    issues.append({
                        'issue': 'PERCENTAGE_MISMATCH',
                        'expected': expected_pct,
                        'actual': actual,
                        'message': f"Percentage should be ${expected_gain:,.0f}/${expected_cost:,.0f} = {expected_pct:.1f}%, but stated as {actual}%"
                    })
        
        # Check tax
        if 'tax' in percentages and 'gain' in financials:
            expected_tax = financials['gain'] * percentages['tax'] / 100
            if 'tax' in financials:
                actual_tax = financials['tax']
                if abs(actual_tax - expected_tax) > 1:
                    issues.append({
                        'issue': 'TAX_MISMATCH',
                        'expected': expected_tax,
                        'actual': actual_tax,
                        'message': f"Tax should be ${financials['gain']:,.0f} × {percentages['tax']}% = ${expected_tax:,.0f}, but stated as ${actual_tax:,.0f}"
                    })
    
    return issues


def verify_math_in_output(output: str) -> Dict:
    """Verify math calculations in OUTPUT."""
    claims = extract_financial_claims(output)
    issues = verify_financial_consistency(claims)
    
    return {
        'claims_found': len(claims),
        'issues': issues,
        'has_errors': len(issues) > 0,
        'claims': claims,
    }


if __name__ == "__main__":
    test_output = """200 shares of AAPL bought at $150 each total $30,000. 
    Currently valued at $180 per share, the total value is $36,000. 
    This yields a $6,000 gain. After applying a 15% tax on the profit, 
    the tax amount is $900, leaving a net gain of $5,100. 
    The total return on investment is 17%."""
    
    print("=== Math Verifier Test ===")
    print(f"Input:\n{test_output}\n")
    
    result = verify_math_in_output(test_output)
    print(f"Claims found: {result['claims_found']}")
    print(f"Has errors: {result['has_errors']}")
    print()
    print("Claims:")
    for c in result['claims']:
        print(f"  [{c['type']}] {c.get('label', '')} = {c.get('value', '')}")
    print()
    if result['issues']:
        print("ISSUES:")
        for issue in result['issues']:
            print(f"  ❌ {issue['issue']}: {issue['message']}")
    else:
        print("✓ No issues found")
