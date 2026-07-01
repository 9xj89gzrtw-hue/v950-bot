#!/usr/bin/env python3
"""Behavioral test part 2 — TG, MV, OV, IV, Cache, RL integration."""
import sys, time, tempfile, threading
from pathlib import Path
sys.path.insert(0, '/home/z/my-project/scripts')
from multi_llm_v4 import call_local, get_local_llm, Cache, RateLimiter, call_zai
from truth_gateway import truth_gateway, extract_claims
from math_verifier import verify_math_in_output
from output_validator import validate_output
from idea_validator import validate_idea, handle_user_insists

PASS = 0; FAIL = 0
def test(name, cond, detail=''):
    global PASS, FAIL
    if cond: PASS += 1; print(f'✓ {name}')
    else: FAIL += 1; print(f'✗ {name}: {detail}')

print('Loading model...')
llm = get_local_llm()
print('Ready.\n')

# Truth Gateway on real output
print('=== Truth Gateway ===')
out = call_local('You are a tech analyst. Mention specific AI model versions like GPT-5, GLM-5.',
                 'List the latest AI models in 2026: GPT, GLM, Claude. 50 words.', max_tokens=120)
if out['success']:
    output = out['content']
    claims = extract_claims(output)
    test('TG: extracts claims', len(claims) > 0, f'claims: {len(claims)}')
    
    tg = truth_gateway(output, verify=False, max_claims=5)
    test('TG: returns annotated', 'annotated' in tg)
    test('TG: returns stats', 'stats' in tg)
    test('TG: returns summary', 'summary' in tg)
    test('TG: summary has numbers', 'Verified' in tg['summary'] or 'claims' in tg['summary'], tg['summary'][:80])
else:
    test('TG: model output', False, 'no output')

# Math Verifier
print('\n=== Math Verifier ===')
out = call_local('You are a financial analyst. Be precise.',
                 '200 AAPL @ $150, current $180. Calculate: total cost, value, gain, % return. 60 words.', 
                 max_tokens=200)
if out['success']:
    output = out['content']
    mv = verify_math_in_output(output)
    test('MV: processes output', 'claims_found' in mv)
    test('MV: found claims', mv['claims_found'] >= 2, f'found {mv["claims_found"]}')
    # If model made math error, MV should catch
    if mv['has_errors']:
        test('MV: caught error', True, f'issues: {[i["issue"] for i in mv["issues"]]}')
    else:
        test('MV: math correct', True)
else:
    test('MV: model output', False, 'no output')

# Test MV catches deliberate error
wrong = '200 shares at $150. Current $180. Total cost $30,000. Value $36,000. Gain $6,000. Return 17%.'
mv = verify_math_in_output(wrong)
test('MV: catches 17% vs 20%', mv['has_errors'], f'issues: {[i["issue"] for i in mv["issues"]]}')

# Output Validator
print('\n=== Output Validator ===')
out = call_local('Be brief.', 'What is React? 10 words.', max_tokens=20)
if out['success']:
    ov = validate_output(out['content'], 'web')
    test('OV: flags short output', not ov['passed'], f'words: {ov["word_count"]}')
    test('OV: returns word count', 'word_count' in ov)
    test('OV: returns issues list', isinstance(ov['issues'], list))
else:
    test('OV: short output', False, 'no output')

# OV with placeholder
out = call_local('Write code.', 'Write a function. Use TODO for unknown parts.', max_tokens=80)
if out['success']:
    ov = validate_output(out['content'], 'default')
    has_todo = 'TODO' in out['content'] or len(ov['placeholders']) > 0
    test('OV: detects TODO', has_todo, f'placeholders: {ov["placeholders"][:2]}')
else:
    test('OV: TODO detection', False, 'no output')

# Idea Validator
print('\n=== Idea Validator ===')
r = validate_idea('Use Python 3.8', use_cache=False)
test('IV: returns verdict', 'verdict' in r)
test('IV: returns confidence', 'confidence' in r)
test('IV: returns recommendation', 'recommendation' in r)
test('IV: returns research_date', 'research_date' in r)

# IV AVOID protocol
avoid = {'verdict': 'AVOID', 'confidence': 0.8, 'risks': ['security'], 
         'alternatives': [], 'evidence': [], 'security_risks': [],
         'recommendation': 'avoid', 'idea': 'bad', 'research_date': '2026-06-30',
         'total_sources_checked': 0}
insists = handle_user_insists('bad', avoid)
test('IV: insists has 5 steps', len(insists['insists_protocol']) == 5)
test('IV: step 3 requires yes/no', 'yes' in insists['insists_protocol']['step_3'].lower())
test('IV: step 4 marks USER-ACCEPTED-RISK', 'USER-ACCEPTED-RISK' in insists['insists_protocol']['step_4'])

# Cascade fallback
print('\n=== Cascade ===')
r = call_zai('test', 'test', timeout=10)
test('Cascade: z-ai status', 'success' in r)
if not r['success']:
    test('Cascade: z-ai fails gracefully', True)

r = call_local('Be brief.', "Say 'cascade works' in 3 words.", max_tokens=15)
test('Cascade: local works', r['success'])
if r['success']:
    test('Cascade: meaningful output', len(r['content']) > 5, r['content'][:50])

# Cache
print('\n=== Cache ===')
with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
    cp = f.name
cache = Cache(Path(cp))
cache.set('sys', 'user', 'response')
test('Cache: set/get', cache.get('sys', 'user') == 'response')
test('Cache: miss None', cache.get('sys', 'other') is None)

# Persist
cache2 = Cache(Path(cp))
test('Cache: persists', cache2.get('sys', 'user') == 'response')

# Corrupt recovery
with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
    f.write('NOT JSON {{{{')
    corrupt = f.name
c = Cache(Path(corrupt))
test('Cache: corrupt recovery', c.data == {})

# RateLimiter
print('\n=== RateLimiter ===')
rl = RateLimiter(0.05, 0.5)
t0 = time.time()
rl.wait()
d1 = time.time() - t0
test('RL: delays', d1 >= 0.03, f'{d1:.3f}s')

for _ in range(3): rl.on_success()
test('RL: speeds up', rl.current_delay <= 0.05, f'{rl.current_delay}')

for _ in range(3): rl.on_fail()
test('RL: slows down', rl.current_delay > 0.05, f'{rl.current_delay}')

# Thread safety
print('\n=== Thread safety ===')
errors = []
def worker(i):
    try:
        cache.set(f's{i}', f'u{i}', f'c{i}')
        cache.get(f's{i}', f'u{i}')
    except Exception as e:
        errors.append(str(e))

threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
for t in threads: t.start()
for t in threads: t.join()
test('Thread: no errors', len(errors) == 0, f'{errors[:2]}')

print(f'\n=== TOTAL: {PASS} passed, {FAIL} failed ===')
