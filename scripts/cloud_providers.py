#!/usr/bin/env python3
"""
Multi-cloud LLM provider support.
Works with free API keys from: Groq, Google AI, Together, Cerebras, OpenRouter.
When user adds a key to .env — provider activates automatically.
"""
import os
import json
import urllib.request
from pathlib import Path
from typing import Dict, Optional

def load_env():
    """Load API keys from .env file."""
    env_path = Path("/home/z/my-project/repo/.env")
    if env_path.exists():
        for line in env_path.read_text().split('\n'):
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env()

PROVIDERS = {
    'groq': {
        'name': 'Groq (Llama 3.3 70B, fastest inference)',
        'env_key': 'GROQ_API_KEY',
        'url': 'https://api.groq.com/openai/v1/chat/completions',
        'models': ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'gemma2-9b-it'],
        'speed': '500+ t/s',
    },
    'google': {
        'name': 'Google AI Studio (Gemini 2.0 Flash)',
        'env_key': 'GOOGLE_API_KEY',
        'url': 'https://generativelanguage.googleapis.com/v1beta/models',
        'models': ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
        'speed': '100+ t/s',
    },
    'together': {
        'name': 'Together AI (Qwen 2.5 72B, DeepSeek R1)',
        'env_key': 'TOGETHER_API_KEY',
        'url': 'https://api.together.xyz/v1/chat/completions',
        'models': ['Qwen/Qwen2.5-72B-Instruct', 'meta-llama/Llama-3.3-70B-Instruct-Turbo'],
        'speed': '200+ t/s',
    },
    'cerebras': {
        'name': 'Cerebras (Llama 3.3 70B, 2000+ t/s)',
        'env_key': 'CEREBRAS_API_KEY',
        'url': 'https://api.cerebras.ai/v1/chat/completions',
        'models': ['llama3.3-70b', 'llama3.1-8b'],
        'speed': '2000+ t/s',
    },
    'openrouter': {
        'name': 'OpenRouter (free models: Llama 70B, Qwen 72B)',
        'env_key': 'OPENROUTER_API_KEY',
        'url': 'https://openrouter.ai/api/v1/chat/completions',
        'models': ['meta-llama/llama-3.3-70b-instruct:free', 'qwen/qwen-2.5-72b-instruct:free'],
        'speed': '100+ t/s',
    },
}


def get_available_providers() -> Dict:
    """Check which providers have API keys configured."""
    available = {}
    for key, p in PROVIDERS.items():
        api_key = os.environ.get(p['env_key'])
        if api_key:
            available[key] = {**p, 'has_key': True, 'api_key': api_key[:8] + '...'}
        else:
            available[key] = {**p, 'has_key': False}
    return available


def call_groq(system: str, user: str, model: str = 'llama-3.3-70b-versatile', max_tokens: int = 500) -> Dict:
    """Call Groq API (Llama 3.3 70B — one of the best open models)."""
    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        return {'success': False, 'error': 'No GROQ_API_KEY in .env'}
    
    payload = json.dumps({
        'model': model,
        'messages': [
            {'role': 'system', 'content': system[:10000]},
            {'role': 'user', 'content': user[:10000]},
        ],
        'max_tokens': max_tokens,
        'temperature': 0.5,
    }).encode()
    
    req = urllib.request.Request(
        'https://api.groq.com/openai/v1/chat/completions',
        data=payload,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
    )
    
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        return {'success': True, 'content': data['choices'][0]['message']['content'],
                'provider': f'groq-{model}', 'tokens': data.get('usage', {})}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def call_google(system: str, user: str, model: str = 'gemini-2.0-flash', max_tokens: int = 500) -> Dict:
    """Call Google AI Studio (Gemini 2.0 Flash)."""
    api_key = os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        return {'success': False, 'error': 'No GOOGLE_API_KEY in .env'}
    
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}'
    payload = json.dumps({
        'contents': [{'parts': [{'text': f'{system}\n\n{user}'}]}],
        'generationConfig': {'maxOutputTokens': max_tokens, 'temperature': 0.5},
    }).encode()
    
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        content = data['candidates'][0]['content']['parts'][0]['text']
        return {'success': True, 'content': content, 'provider': f'google-{model}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def call_openrouter(system: str, user: str, model: str = 'meta-llama/llama-3.3-70b-instruct:free', max_tokens: int = 500) -> Dict:
    """Call OpenRouter (free models available)."""
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        return {'success': False, 'error': 'No OPENROUTER_API_KEY in .env'}
    
    payload = json.dumps({
        'model': model,
        'messages': [
            {'role': 'system', 'content': system[:10000]},
            {'role': 'user', 'content': user[:10000]},
        ],
        'max_tokens': max_tokens,
    }).encode()
    
    req = urllib.request.Request(
        'https://openrouter.ai/api/v1/chat/completions',
        data=payload,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
    )
    
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        return {'success': True, 'content': data['choices'][0]['message']['content'],
                'provider': f'openrouter-{model}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def best_available() -> Optional[str]:
    """Return the best available provider name."""
    available = get_available_providers()
    # Priority: groq (70B, 500t/s) > cerebras (70B, 2000t/s) > together > openrouter > google
    for p in ['groq', 'cerebras', 'together', 'openrouter', 'google']:
        if available.get(p, {}).get('has_key'):
            return p
    return None


if __name__ == '__main__':
    print('=== Cloud Providers Status ===\n')
    available = get_available_providers()
    for key, p in available.items():
        status = '✓ READY' if p['has_key'] else '✗ No key'
        print(f'{p["name"]}')
        print(f'  Status: {status}')
        print(f'  Models: {", ".join(p["models"])}')
        print(f'  Speed: {p["speed"]}')
        print()
    
    best = best_available()
    if best:
        print(f'Best available: {best}')
    else:
        print('No cloud providers configured.')
        print('\nTo activate, add API keys to /home/z/my-project/repo/.env:')
        print('  GROQ_API_KEY=gsk_...        (https://console.groq.com)')
        print('  GOOGLE_API_KEY=AI...        (https://aistudio.google.com)')
        print('  OPENROUTER_API_KEY=sk-or... (https://openrouter.ai/keys)')
        print('  TOGETHER_API_KEY=...        (https://api.together.ai)')
        print('  CEREBRAS_API_KEY=csk-...    (https://cloud.cerebras.ai)')
