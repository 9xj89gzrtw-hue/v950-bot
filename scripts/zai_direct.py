#!/usr/bin/env python3
"""
Direct z.ai API access — bypasses CLI subprocess overhead.
10x faster than z-ai CLI, no subprocess, no JSON file parsing.
"""
import json
import urllib.request
from pathlib import Path
from typing import Optional, Dict

# Load config once
_CONFIG = None

def _get_config():
    global _CONFIG
    if _CONFIG is None:
        for path in ['/etc/.z-ai-config', str(Path.home() / '.z-ai-config')]:
            if Path(path).exists():
                _CONFIG = json.loads(Path(path).read_text())
                break
        if _CONFIG is None:
            raise RuntimeError("No .z-ai-config found")
    return _CONFIG


def chat(system_prompt: str, user_prompt: str, model: str = 'glm-4-plus', 
         max_tokens: int = 2000, temperature: float = 0.5) -> Dict:
    """
    Direct API call to z.ai — no subprocess, no CLI overhead.
    Returns dict with 'success', 'content', 'provider', 'usage'.
    """
    config = _get_config()
    
    url = config['baseUrl'] + '/chat/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {config["apiKey"]}',
        'X-Z-AI-From': 'Z',
        'X-Chat-Id': config['chatId'],
        'X-User-Id': config['userId'],
    }
    if config.get('token'):
        headers['X-Token'] = config['token']
    
    payload = json.dumps({
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt[:30000]},
            {'role': 'user', 'content': user_prompt[:30000]},
        ],
        'max_tokens': max_tokens,
        'temperature': temperature,
        'thinking': {'type': 'disabled'},
    }).encode()
    
    req = urllib.request.Request(url, data=payload, headers=headers)
    
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        return {
            'success': True,
            'content': data['choices'][0]['message']['content'],
            'provider': f'zai-direct-{data.get("model", model)}',
            'usage': data.get('usage', {}),
        }
    except Exception as e:
        return {'success': False, 'error': str(e), 'provider': 'zai-direct'}


def web_search(query: str, num: int = 5) -> list:
    """Direct web search via z.ai API."""
    config = _get_config()
    
    url = config['baseUrl'] + '/functions/run'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {config["apiKey"]}',
        'X-Z-AI-From': 'Z',
        'X-Chat-Id': config['chatId'],
        'X-User-Id': config['userId'],
    }
    if config.get('token'):
        headers['X-Token'] = config['token']
    
    payload = json.dumps({
        'name': 'web_search',
        'parameters': {'query': query, 'num': num},
    }).encode()
    
    req = urllib.request.Request(url, data=payload, headers=headers)
    
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        return data if isinstance(data, list) else []
    except:
        return []


if __name__ == '__main__':
    import time
    
    print('=== Direct z.ai API Test ===\n')
    
    # Test 1: Simple chat
    t0 = time.time()
    r = chat('You are helpful.', 'What is 17 * 23? Show steps. End with Answer: X', max_tokens=200)
    elapsed = time.time() - t0
    
    if r['success']:
        print(f'✓ Response in {elapsed:.1f}s (vs 50s for local 14B)')
        print(f'Provider: {r["provider"]}')
        print(f'Usage: {r["usage"]}')
        print(f'Content: {r["content"][:300]}')
    else:
        print(f'✗ Error: {r["error"]}')
    
    print('\n=== Math Test ===')
    r = chat('Solve step by step. End with Answer: X', 
             '200 AAPL @ $150, current $180. Calculate % return. End with Answer: X', max_tokens=200)
    if r['success']:
        has_20 = '20%' in r['content']
        print(f'Correct (20%): {has_20}')
        print(f'Response: {r["content"][:200]}')
