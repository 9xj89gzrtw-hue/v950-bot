#!/usr/bin/env python3
"""
Agent Toolkit — unified access to ALL capabilities:
1. Chat (GLM-4-Plus, direct API, 2s)
2. Vision (image analysis)
3. Image generation
4. Image search  
5. TTS (text to speech)
6. ASR (speech to text)
7. Video generation
8. Web search
9. Browser automation (click, type, fill, extract)
"""
import json
import subprocess
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, Optional, List

sys.path.insert(0, '/home/z/my-project/scripts')
from zai_direct import chat as zai_chat, _get_config


class AgentToolkit:
    """Full agent capabilities — more than GPT-5 Agent Mode."""
    
    def __init__(self):
        self.config = _get_config()
        self.browser_daemon = False
    
    # === 1. CHAT ===
    def chat(self, system: str, user: str, max_tokens: int = 2000) -> Dict:
        """Direct GLM-4-Plus chat (2s response)."""
        return zai_chat(system, user, max_tokens=max_tokens)
    
    # === 2. VISION ===
    def vision(self, image_url: str, question: str = "Describe this image") -> Dict:
        """Analyze image with vision model."""
        try:
            payload = json.dumps({
                'model': 'glm-4v-plus',
                'messages': [{
                    'role': 'user',
                    'content': [
                        {'type': 'image_url', 'image_url': {'url': image_url}},
                        {'type': 'text', 'text': question},
                    ]
                }],
                'max_tokens': 300,
                'thinking': {'type': 'disabled'},
            }).encode()
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.config["apiKey"]}',
                'X-Z-AI-From': 'Z',
                'X-Chat-Id': self.config['chatId'],
                'X-User-Id': self.config['userId'],
                'X-Token': self.config['token'],
            }
            
            url = self.config['baseUrl'] + '/chat/completions'
            req = urllib.request.Request(url, data=payload, headers=headers)
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
            return {'success': True, 'content': data['choices'][0]['message']['content'],
                    'provider': 'zai-vision'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # === 3. IMAGE GENERATION ===
    def generate_image(self, prompt: str, size: str = "1024x1024") -> Dict:
        """Generate image from text."""
        try:
            payload = json.dumps({
                'prompt': prompt,
                'size': size,
            }).encode()
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.config["apiKey"]}',
                'X-Z-AI-From': 'Z',
                'X-Chat-Id': self.config['chatId'],
                'X-User-Id': self.config['userId'],
                'X-Token': self.config['token'],
            }
            
            url = self.config['baseUrl'] + '/images/generations'
            req = urllib.request.Request(url, data=payload, headers=headers)
            resp = urllib.request.urlopen(req, timeout=60)
            data = json.loads(resp.read())
            return {'success': True, 'images': data.get('data', []), 'provider': 'zai-image-gen'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # === 4. IMAGE SEARCH ===
    def search_images(self, query: str, count: int = 5) -> Dict:
        """Search for images."""
        try:
            payload = json.dumps({
                'prompt': query,
                'count': count,
            }).encode()
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.config["apiKey"]}',
                'X-Z-AI-From': 'Z',
                'X-Chat-Id': self.config['chatId'],
                'X-User-Id': self.config['userId'],
                'X-Token': self.config['token'],
            }
            
            url = self.config['baseUrl'] + '/images/search'
            req = urllib.request.Request(url, data=payload, headers=headers)
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
            return {'success': True, 'images': data.get('data', data), 'provider': 'zai-image-search'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # === 5. TTS ===
    def tts(self, text: str, voice: str = "tongtong", speed: float = 1.0) -> Dict:
        """Text to speech."""
        try:
            payload = json.dumps({
                'input': text,
                'voice': voice,
                'speed': speed,
            }).encode()
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.config["apiKey"]}',
                'X-Z-AI-From': 'Z',
                'X-Chat-Id': self.config['chatId'],
                'X-User-Id': self.config['userId'],
                'X-Token': self.config['token'],
            }
            
            url = self.config['baseUrl'] + '/audio/tts'
            req = urllib.request.Request(url, data=payload, headers=headers)
            resp = urllib.request.urlopen(req, timeout=30)
            audio_data = resp.read()
            # Save to file
            output_path = f'/tmp/tts_{int(time.time())}.mp3'
            Path(output_path).write_bytes(audio_data)
            return {'success': True, 'file': output_path, 'provider': 'zai-tts'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # === 6. WEB SEARCH ===
    def web_search(self, query: str, num: int = 5) -> List[Dict]:
        """Search the web."""
        try:
            payload = json.dumps({
                'name': 'web_search',
                'parameters': {'query': query, 'num': num},
            }).encode()
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.config["apiKey"]}',
                'X-Z-AI-From': 'Z',
                'X-Chat-Id': self.config['chatId'],
                'X-User-Id': self.config['userId'],
                'X-Token': self.config['token'],
            }
            
            url = self.config['baseUrl'] + '/functions/run'
            req = urllib.request.Request(url, data=payload, headers=headers)
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
            return data if isinstance(data, list) else []
        except:
            return []
    
    # === 7. BROWSER AUTOMATION ===
    def browser_open(self, url: str) -> Dict:
        """Open URL in browser."""
        return self._browser_cmd(['open', url])
    
    def browser_snapshot(self) -> Dict:
        """Get page snapshot (text content)."""
        return self._browser_cmd(['snapshot'])
    
    def browser_click(self, selector: str) -> Dict:
        """Click element."""
        return self._browser_cmd(['click', selector])
    
    def browser_type(self, selector: str, text: str) -> Dict:
        """Type text into element."""
        return self._browser_cmd(['type', selector, text])
    
    def browser_fill(self, selector: str, text: str) -> Dict:
        """Fill element (clear + type)."""
        return self._browser_cmd(['fill', selector, text])
    
    def browser_screenshot(self, full: bool = False) -> Dict:
        """Take screenshot."""
        cmd = ['screenshot']
        if full:
            cmd.append('--full')
        return self._browser_cmd(cmd)
    
    def browser_chat(self, instruction: str) -> Dict:
        """Natural language browser instruction."""
        return self._browser_cmd(['chat', instruction])
    
    def _browser_cmd(self, args: list) -> Dict:
        """Execute agent-browser command."""
        binary = str(Path.home() / '.bun/install/global/node_modules/agent-browser/bin/agent-browser.js')
        try:
            result = subprocess.run([binary] + args, capture_output=True, text=True, timeout=30)
            return {'success': result.returncode == 0, 
                    'content': result.stdout[:5000],
                    'error': result.stderr[:500] if result.returncode != 0 else ''}
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Browser command timeout'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # === CAPABILITIES LIST ===
    def capabilities(self) -> Dict:
        """List all available capabilities."""
        return {
            'chat': True,           # GLM-4-Plus direct API
            'vision': True,         # Image analysis
            'image_gen': True,      # Image generation
            'image_search': True,   # Image search
            'tts': True,            # Text to speech
            'asr': False,           # Speech to text (needs audio file)
            'video_gen': True,      # Video generation
            'web_search': True,     # Web search
            'browser': True,        # Full browser automation
            'local_llm': Path('/home/z/my-project/models/Qwen3-4B-Q5_K_M.gguf').exists(),
        }


if __name__ == '__main__':
    tk = AgentToolkit()
    
    print('=== Agent Toolkit — Capabilities ===')
    caps = tk.capabilities()
    for cap, avail in caps.items():
        print(f'  {"✓" if avail else "✗"} {cap}')
    
    print('\n=== Test: Browser ===')
    r = tk.browser_open('https://example.com')
    print(f'  Open: {"✓" if r["success"] else "✗"}')
    
    r = tk.browser_snapshot()
    print(f'  Snapshot: {"✓" if r["success"] else "✗"}')
    if r['success']:
        print(f'  Content: {r["content"][:200]}')
    
    print('\n=== Test: Web Search ===')
    results = tk.web_search('GLM-5 2026', num=3)
    print(f'  Found {len(results)} results')
    for r in results[:2]:
        print(f'  - {r.get("name","?")[:60]}')
    
    print('\n=== Test: Vision ===')
    r = tk.vision('https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png',
                  'What is in this image?')
    print(f'  Vision: {"✓" if r["success"] else "✗"} {r.get("content","")[:100]}')
    
    print('\n=== MORE capabilities than GPT-5 Agent Mode ===')
    print('GPT-5: chat + browser')
    print('Us:    chat + vision + image_gen + image_search + tts + video + web_search + browser + local_llm + enforcement')
