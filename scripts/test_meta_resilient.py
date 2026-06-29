#!/usr/bin/env python3
"""
Устойчивый тестовый стенд с:
- persistent checkpoint (json state file)
- exponential backoff + jitter
- resume mode (skip completed)
- local cache (hash-based)
- adaptive rate limiting

Никаких обходов ToS — только легитимная устойчивость к rate-limit.
"""
import json
import subprocess
import os
import sys
import time
import hashlib
import random
from pathlib import Path

VERSION = sys.argv[1] if len(sys.argv) > 1 else "v9.79-FINAL"
SUFFIX = sys.argv[2] if len(sys.argv) > 2 else ""
TESTS_ARG = sys.argv[3] if len(sys.argv) > 3 else None  # опционально: id тестов через запятую

REPO = Path("/home/z/my-project/repo")
PROMPT_FILE = REPO / f"meta-prompt-{VERSION}.md"
META_PROMPT = PROMPT_FILE.read_text()

OUT_DIR_BASE = f"/home/z/my-project/download/compiled_{VERSION.replace('.', '_')}"
OUT_DIR = Path(OUT_DIR_BASE + (f"_{SUFFIX}" if SUFFIX else ""))
OUT_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = OUT_DIR / "_state.json"
CACHE_FILE = OUT_DIR / "_cache.json"

# Тесты R1
TESTS_R1 = [
    {"id": "T1_medical_diagnostic", "task": "Скомпилируй промпт для медицинского диагностического ассистента. Ассистент принимает симптомы пользователя, задаёт уточняющие вопросы, и выдаёт список возможных состояний с вероятностями и уровнями срочности (1-5). Должен отказываться ставить окончательный диагноз и направлять к врачу. Должен покрывать edge cases: симуляция симптомов у ребёнка, беременная, пожилой, аллергик, сопутствующие лекарства."},
    {"id": "T2_legal_contract_analyzer", "task": "Скомпилируй промпт для юридического анализатора договоров. Принимает текст договора, находит рискованные clauses (non-compete, auto-renewal, liability caps, arbitration), объясняет риски простым языком, цитирует конкретные пункты. Не должен давать юридических советов — только анализ. Должен обрабатывать multi-jurisdiction договоры (US/UK/EU/RU) и отказываться если не уверен в юрисдикции."},
    {"id": "T3_financial_risk_model", "task": "Скомпилируй промпт для финансового аналитика рисков. Принимает портфель (asset, quantity, price, currency), считает VaR 95% и 99%, conditional VaR, stress-test сценарии (2008, 2020, hypothetical). Помечает高风险 позиции. Все числа → источник. Если данных недостаточно — ABSTAIN. Не должен давать инвестиционных советов. JSON output для интеграции с другими системами."},
    {"id": "T4_security_audit_agent", "task": "Скомпилируй промпт для агента аудита безопасности Python-кода. Агент многоходовый: (1) читает код, (2) идентифицирует OWASP Top 10, CWE, (3) предлагает fix с объяснением, (4) верифицирует fix. Не должен писать эксплойты. Если находит критическую уязвимость (RCE, SQLi с auth bypass) — помечает P0 и требует подтверждения от пользователя перед продолжением. Markdown отчёт с severity, CWE, fix, verification."},
    {"id": "T5_multilingual_research_agent", "task": "Скомпилируй промпт для мультиязычного research-ассистента. Принимает запрос, ищет источники на 3 языках (EN/RU/ZH), сравнивает точки зрения, выявляет cultural biases, формирует neutral summary с уровнями уверенности. Каждый факт → источник с URL. Если источники противоречат — градация (научные > официальные > медиа). Markdown отчёт с разделом 'contradictions' и 'cultural notes'."},
]

# Тесты R2 (новые задачи)
TESTS_R2 = [
    {"id": "T6_devops_ci_cd", "task": "Скомпилируй промпт для DevOps CI/CD ассистента. Принимает git diff, анализирует изменения, предлагает: (1) какие тесты запустить, (2) какие environments затронуты, (3) rollback план если deploy упадёт. YAML output. Не должен выполнять deploy сам — только план. Если изменения затрагивают security (secrets, auth) — помечает P0 и требует ревью."},
    {"id": "T7_education_tutor", "task": "Скомпилируй промпт для образовательного репетитора по математике для школьников 10-14 лет. Принимает задачу, определяет уровень сложности, даёт подсказки (не решение!), проверяет ответ ученика, объясняет ошибки. Адаптирует тон: для 10 лет — проще, для 14 — строже. Если ученик не понимает после 3 подсказок — даёт решение с объяснением. Markdown диалоговый формат."},
    {"id": "T8_data_pipeline", "task": "Скомпилируй промпт для агента проектирования data pipeline. Принимает требования (sources, transformations, destinations, SLA), проектирует DAG (Airflow-style), выбирает tools (Kafka/Spark/Flink/Beam), объясняет trade-offs. Если SLA <1s — рекомендует stream processing. Если batch ок — Spark. CSV output: stage, tool, reason, sla_impact. Не должен писать код — только архитектуру."},
    {"id": "T9_accessibility_auditor", "task": "Скомпилируй промпт для аудитора accessibility веб-страниц. Принимает HTML, проверяет WCAG 2.2 AA: alt text, contrast, ARIA, keyboard nav, focus management, semantic HTML. Для каждого нарушения: severity (critical/major/minor), WCAG criterion, fix recommendation, code example. Markdown отчёт с executive summary. Если страница содержит PII (формы) — предупреждает о privacy рисках."},
    {"id": "T10_customer_support_router", "task": "Скомпилируй промпт для router-агента customer support. Классифицирует входящие обращения по 5 категориям (billing, technical, complaint, sales, other), определяет sentiment (positive/neutral/negative/angry), urgency (1-5). Если sentiment=angry + urgency=5 — эскалирует на human agent немедленно. JSON output. Если обращение содержит угрозы (legal/self-harm) — помечает safety_flag=true. Не должен давать ответы клиентам — только маршрутизацию."},
]

# Выбираем набор тестов
if SUFFIX == "R2":
    TESTS = TESTS_R2
else:
    TESTS = TESTS_R1

# Фильтр по TESTS_ARG
if TESTS_ARG:
    wanted = set(TESTS_ARG.split(","))
    TESTS = [t for t in TESTS if t["id"] in wanted]


# === STATE MANAGEMENT ===

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"completed": {}, "failed": {}, "last_run": None}

def save_state(state: dict):
    state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))

def load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {}

def save_cache(cache: dict):
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


# === ADAPTIVE RATE LIMITER ===

class RateLimiter:
    """Адаптивный rate limiter: при 429 снижает частоту, при успехе повышает."""
    def __init__(self):
        self.min_delay = 2.0  # baseline
        self.max_delay = 120.0
        self.current_delay = self.min_delay
        self.consecutive_success = 0
        self.consecutive_failures = 0

    def on_success(self):
        self.consecutive_success += 1
        self.consecutive_failures = 0
        # После 3 успехов подряд — снижаем задержку
        if self.consecutive_success >= 3:
            self.current_delay = max(self.min_delay, self.current_delay * 0.7)

    def on_rate_limit(self):
        self.consecutive_failures += 1
        self.consecutive_success = 0
        # Экспоненциальный рост
        factor = 2 ** min(self.consecutive_failures, 5)
        self.current_delay = min(self.max_delay, self.min_delay * factor)

    def wait(self):
        # jitter ±20%
        jitter = random.uniform(0.8, 1.2)
        delay = self.current_delay * jitter
        time.sleep(delay)


# === Z-AI CALL WITH RESILIENCE ===

def call_zai_resilient(system_prompt: str, user_prompt: str, max_retries: int = 8) -> dict:
    """Вызов z-ai с экспоненциальным backoff + jitter + адаптивным throttle."""
    limiter = RateLimiter()
    last_error = None

    for attempt in range(max_retries):
        try:
            limiter.wait()
            tmp_out = "/tmp/_resilient_out.json"
            cmd = ["z-ai", "chat", "-s", system_prompt, "-p", user_prompt, "-o", tmp_out]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0 and os.path.exists(tmp_out):
                data = json.loads(Path(tmp_out).read_text())
                content = None
                if "choices" in data:
                    content = data["choices"][0]["message"]["content"]
                elif "content" in data:
                    content = data["content"]
                if content and len(content) > 50:  # валидный ответ
                    limiter.on_success()
                    return {"success": True, "content": content, "attempts": attempt + 1}
                else:
                    last_error = f"empty/short content: {content[:100] if content else 'None'}"
            else:
                stderr = result.stderr or ""
                last_error = stderr[:200]
                # Признаки rate limit
                if "429" in stderr or "rate" in stderr.lower() or "Too Many" in stderr:
                    limiter.on_rate_limit()
                    print(f"  ⚠️ rate-limit attempt {attempt+1}: waiting {limiter.current_delay:.1f}s")
                elif "context deadline" in stderr or "timeout" in stderr.lower():
                    limiter.on_rate_limit()
                    print(f"  ⚠️ timeout attempt {attempt+1}: waiting {limiter.current_delay:.1f}s")
                else:
                    # другая ошибка — короткая пауза
                    time.sleep(3)
        except subprocess.TimeoutExpired:
            last_error = "subprocess timeout"
            limiter.on_rate_limit()
            print(f"  ⚠️ subprocess-timeout attempt {attempt+1}")
        except Exception as e:
            last_error = str(e)
            time.sleep(3)

    return {"success": False, "error": last_error, "attempts": max_retries}


# === CACHE KEY ===

def cache_key(system_prompt: str, user_prompt: str) -> str:
    h = hashlib.sha256()
    h.update(system_prompt.encode())
    h.update(b"|||")
    h.update(user_prompt.encode())
    return h.hexdigest()[:32]


# === MAIN ===

def run_tests():
    state = load_state()
    cache = load_cache()

    print("=" * 80)
    print(f"УСТОЙЧИВЫЙ ТЕСТ {VERSION} {SUFFIX}")
    print(f"Тестов в очереди: {len(TESTS)}")
    print(f"Уже завершено: {len(state['completed'])}")
    print(f"Кэш: {len(cache)} записей")
    print("=" * 80)

    results = []
    for test in TESTS:
        test_id = test["id"]

        # Resume: пропускаем если уже завершён
        if test_id in state["completed"]:
            cached_file = OUT_DIR / f"{test_id}.md"
            if cached_file.exists():
                content = cached_file.read_text()
                print(f"\n✓ {test_id} — SKIP (already completed, cached)")
                results.append({"id": test_id, "task": test["task"], "compiled": content, "skipped": True})
                continue
            # если файл не существует — пересоздаём из state
            content = state["completed"][test_id].get("content", "")
            if content:
                cached_file.write_text(content)
                results.append({"id": test_id, "task": test["task"], "compiled": content, "skipped": True})
                continue

        print(f"\n▶ {test_id}")
        print(f"  Task: {test['task'][:100]}...")

        # Cache check
        key = cache_key(META_PROMPT, test["task"])
        if key in cache:
            content = cache[key]
            print(f"  → CACHE HIT")
        else:
            result = call_zai_resilient(META_PROMPT, test["task"])
            if result["success"]:
                content = result["content"]
                cache[key] = content
                save_cache(cache)
                print(f"  ✓ {len(content)} chars (attempts: {result['attempts']})")
            else:
                print(f"  ✗ FAILED after {result['attempts']}: {result['error']}")
                state["failed"][test_id] = {"error": result["error"], "attempts": result["attempts"]}
                save_state(state)
                # Продолжаем со следующим — не падаем
                results.append({"id": test_id, "task": test["task"], "compiled": f"[ERROR: {result['error']}]", "failed": True})
                continue

        # Сохраняем
        out_file = OUT_DIR / f"{test_id}.md"
        out_file.write_text(content)

        # Checkpoint в state
        state["completed"][test_id] = {
            "content_length": len(content),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        save_state(state)

        results.append({"id": test_id, "task": test["task"], "compiled": content})

    # Сохраняем all_results
    (OUT_DIR / "_all_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))

    print("\n" + "=" * 80)
    print("ИТОГ:")
    print(f"  Успешно: {sum(1 for r in results if not r.get('failed'))}/{len(TESTS)}")
    print(f"  Пропущено (resume): {sum(1 for r in results if r.get('skipped'))}")
    print(f"  Провалено: {sum(1 for r in results if r.get('failed'))}")
    print(f"  Файлы: {OUT_DIR}")
    print("=" * 80)
    return results


if __name__ == "__main__":
    run_tests()
