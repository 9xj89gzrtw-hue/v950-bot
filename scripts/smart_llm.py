#!/usr/bin/env python3
"""
Smart LLM router — automatically switches between providers to avoid rate limits.
Priority: z-ai direct (best, fast) → Pollinations (no limit) → local (always)
When rate limited: auto-switch to next provider, retry original after cooldown.
"""
import json
import urllib.request
import time
import os
import sys
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, '/home/z/my-project/scripts')


class SmartLLM:
    def __init__(self):
        self.providers = {}
        self.cooldowns = {}  # provider -> until timestamp
        self._load_zai()
        self._load_pollinations()
        self._load_local()
        
    def _load_zai(self):
        """Load z.ai direct API config."""
        try:
            config = json.load(open('/etc/.z-ai-config'))
            self.providers['zai'] = {
                'config': config,
                'available': True,
                'priority': 1,
            }
        except:
            self.providers['zai'] = {'available': False, 'priority': 1}
    
    def _load_pollinations(self):
        """Pollinations — always available, no auth."""
        self.providers['pollinations'] = {
            'available': True,
            'priority': 2,
        }
    
    def _load_local(self):
        """Local model — always available."""
        model_path = None
        for p in ['/home/z/my-project/models/Qwen3-4B-Q5_K_M.gguf',
                  '/home/z/my-project/models/Qwen2.5-14B-Instruct-Q2_K.gguf']:
            if Path(p).exists():
                model_path = p
                break
        self.providers['local'] = {
            'available': model_path is not None,
            'priority': 3,
            'model_path': model_path,
            'llm': None,
        }
    
    def _call_zai(self, system: str, user: str, max_tokens: int = 2000) -> Dict:
        """Direct z.ai API call."""
        config = self.providers['zai']['config']
        url = config['baseUrl'] + '/chat/completions'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {config["apiKey"]}',
            'X-Z-AI-From': 'Z',
            'X-Chat-Id': config['chatId'],
            'X-User-Id': config['userId'],
            'X-Token': config['token'],
        }
        payload = json.dumps({
            'model': 'glm-4-plus',
            'messages': [
                {'role': 'system', 'content': system[:30000]},
                {'role': 'user', 'content': user[:30000]},
            ],
            'max_tokens': max_tokens,
            'thinking': {'type': 'disabled'},
        }).encode()
        req = urllib.request.Request(url, data=payload, headers=headers)
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        return {'success': True, 'content': data['choices'][0]['message']['content'],
                'provider': 'zai-glm-4-plus'}
    
    def _call_pollinations(self, system: str, user: str, max_tokens: int = 2000) -> Dict:
        """Pollinations API call."""
        payload = json.dumps({
            'model': 'openai',
            'messages': [
                {'role': 'system', 'content': system[:5000]},
                {'role': 'user', 'content': user[:5000]},
            ],
            'max_tokens': max_tokens,
            'reasoning_effort': 'low',
        }).encode()
        req = urllib.request.Request(
            'https://text.pollinations.ai/openai',
            data=payload,
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'},
            method='POST',
        )
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        content = data['choices'][0]['message'].get('content') or ''
        if not content:
            content = data['choices'][0]['message'].get('reasoning', '')
        return {'success': True, 'content': content, 'provider': 'pollinations'}
    
    def _call_local(self, system: str, user: str, max_tokens: int = 2000) -> Dict:
        """Local model call."""
        p = self.providers['local']
        if p['llm'] is None:
            from llama_cpp import Llama
            p['llm'] = Llama(model_path=p['model_path'], n_ctx=4096, n_threads=4, 
                            verbose=False, flash_attn=True)
        out = p['llm'].create_chat_completion(
            messages=[
                {'role': 'system', 'content': system[:3000]},
                {'role': 'user', 'content': user[:4000]},
            ],
            max_tokens=min(max_tokens, 2000),
            temperature=0.5,
        )
        return {'success': True, 'content': out['choices'][0]['message']['content'],
                'provider': 'local'}
    
    def chat(self, system: str, user: str, max_tokens: int = 2000) -> Dict:
        """
        Smart chat — auto-switches providers to avoid rate limits.
        Priority: zai (best) → pollinations (no limit) → local (always)
        """
        now = time.time()
        
        # Sort by priority
        for name in sorted(self.providers.keys(), key=lambda k: self.providers[k]['priority']):
            p = self.providers[name]
            if not p['available']:
                continue
            
            # Check cooldown
            if name in self.cooldowns and self.cooldowns[name] > now:
                continue
            
            # Try this provider
            try:
                if name == 'zai':
                    return self._call_zai(system, user, max_tokens)
                elif name == 'pollinations':
                    return self._call_pollinations(system, user, max_tokens)
                elif name == 'local':
                    return self._call_local(system, user, max_tokens)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    # Rate limited — cooldown 60s
                    self.cooldowns[name] = now + 60
                    print(f'  ⚠️ {name} rate limited, cooldown 60s')
                    continue
                else:
                    print(f'  ⚠️ {name} error: HTTP {e.code}')
                    continue
            except Exception as e:
                print(f'  ⚠️ {name} error: {str(e)[:80]}')
                continue
        
        return {'success': False, 'error': 'All providers failed or on cooldown',
                'provider': 'none'}
    
    def status(self) -> Dict:
        """Get provider status."""
        now = time.time()
        status = {}
        for name, p in self.providers.items():
            status[name] = {
                'available': p['available'],
                'on_cooldown': name in self.cooldowns and self.cooldowns[name] > now,
                'cooldown_remaining': max(0, int(self.cooldowns.get(name, 0) - now)),
                'priority': p['priority'],
            }
        return status


if __name__ == '__main__':
    llm = SmartLLM()
    
    print('=== Smart LLM Router ===\n')
    print('Provider status:')
    for name, s in llm.status().items():
        cd = f' (cooldown {s["cooldown_remaining"]}s)' if s['on_cooldown'] else ''
        print(f'  {name:15s} available={s["available"]} priority={s["priority"]}{cd}')
    
    print('\n=== Test: 5 rapid requests ===')
    for i in range(5):
        r = llm.chat('You are helpful.', f'Say "test {i+1}" in 3 words', max_tokens=15)
        if r['success']:
            print(f'  {i+1}. ✓ {r["provider"]}: {r["content"][:30]}')
        else:
            print(f'  {i+1}. ✗ {r.get("error", "")[:60]}')
        time.sleep(0.3)
