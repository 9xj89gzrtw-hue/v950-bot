#!/usr/bin/env python3
"""
9 сложных задач: 3 website, 3 investing, 3 AI money-making.
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
SUFFIX = "WEB_INV_AIMONEY"  # фиксированный суффикс

REPO = Path("/home/z/my-project/repo")
PROMPT_FILE = REPO / f"meta-prompt-{VERSION}.md"
META_PROMPT = PROMPT_FILE.read_text()

OUT_DIR = Path(f"/home/z/my-project/download/compiled_{VERSION.replace('.', '_')}_{SUFFIX}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = OUT_DIR / "_state.json"
CACHE_FILE = OUT_DIR / "_cache.json"

TESTS = [
    # === WEBSITES (3) ===
    {
        "id": "W1_saas_landing_builder",
        "task": "Скомпилируй промпт для агента генерации SaaS landing pages. Принимает: продукт (название, категория, целевая аудитория, ключевые фичи 3-5, цена). Генерирует: hero section с UVP, problem-solution блок, features grid с иконками, pricing table (3 tier: free/pro/enterprise), social proof placeholder, FAQ, CTA. Next.js 14 App Router + Tailwind + shadcn/ui компоненты. Accessibility WCAG 2.2 AA. SEO meta tags + JSON-LD. Адаптивный (mobile-first). Не должен писать backend — только frontend. Markdown с встроенными JSX-блоками.",
    },
    {
        "id": "W2_ecommerce_product_page",
        "task": "Скомпилируй промпт для агента генерации e-commerce product pages. Принимает: product (name, brand, price, currency, SKU, images URLs, variants, description). Генерирует: product schema.org JSON-LD, image gallery с zoom, variant selector (size/color), add-to-cart с optimistic UI, reviews section (aggregateRating), related products grid, breadcrumbs. React Server Components + streaming. SEO: canonical URL, hreflang для multi-region. GDPR cookie banner hook. Если цена содержит VAT — отдельный расчёт для EU/US/UK. Markdown с code blocks.",
    },
    {
        "id": "W3_admin_dashboard",
        "task": "Скомпилируй промпт для агента проектирования admin dashboards. Принимает: domain (CRM/Analytics/Finance/HR), data sources (Postgres/MongoDB/API/flat files), required KPIs. Проектирует: layout (sidebar + topbar + content), navigation tree, 5-7 widget types (chart types chosen by data shape), filter system, export to CSV/PDF/Excel, role-based access (admin/manager/viewer), audit log. TypeScript типы для всех сущностей. Shadcn/ui + recharts. Если KPI требует real-time — WebSocket. Lazy-load для тяжёлых виджетов. Markdown архитектурный документ с диаграммами Mermaid.",
    },
    # === INVESTING (3) ===
    {
        "id": "I1_portfolio_rebalancer",
        "task": "Скомпилируй промпт для агента ребалансировки инвестиционного портфеля. Принимает: текущие позиции (ticker, qty, cost_basis), целевая аллокация (проценты по классам: stocks/bonds/REITs/commodity/cash), ограничения (tax-loss harvesting окно, min trade size, wash sale rule). Считает: drift от target, налоговые последствия продажи (short-term vs long-term), предлагает sell/buy ордера с минимальным налоговым impact. Disclaimer: не инвестиционный совет. SEC/FINRA compliance. JSON output для интеграции с брокером. Если drift <5% — no action. Если >20% — urgent rebalance. Исторические цены через Yahoo Finance API.",
    },
    {
        "id": "I2_DCF_valuation",
        "task": "Скомпилируй промпт для агента DCF (discounted cash flow) оценки компаний. Принимает: ticker, финансовые отчёты за 5 лет (revenue, EBITDA, FCF, capex, working capital changes), WACC assumptions, terminal growth rate. Считает: projected FCF на 10 лет, terminal value, enterprise value, equity value, per-share value. Сравнивает с текущей ценой (overvalued/undervalued/fair). Sensitivity analysis: WACC ±2%, terminal growth ±1%. Monte Carlo симуляция 1000 сценариев. Не финансовый совет. SEC disclaimers. Markdown отчёт с таблицами и графиками matplotlib.",
    },
    {
        "id": "I3_crypto_arb_scanner",
        "task": "Скомпилируй промпт для агента-сканера крипто-арбитража. Принимает: список бирж (Binance/Bybit/OKX/Kraken/Coinbase), список пар (BTC/USDT, ETH/USDT, SOL/USDT, top-50). Сканирует: bid/ask спреды, считает triangular arb (A→B→C→A), cross-exchange arb с учётом комиссий (taker 0.1%, withdrawal fees, network confirmations). Фильтрует: profit >0.3% after fees, volume >$100k, latency <2s. Вывод: top-10 возможностей JSON с exchange pair, profit %, fees breakdown, estimated execution time. Не финансовый совет. Предупреждение о рисках (slippage, flash crash, MEV). Если данные stale >30s — помечает stale_flag.",
    },
    # === AI MONEY-MAKING (3) ===
    {
        "id": "A1_content_factory",
        "task": "Скомпилируй промпт для агента content factory (faceless YouTube channel). Принимает: ниша (финансы/технологии/мотивация/история), целевая аудитория, tone of voice. Генерирует: 10 идей видео с potential CTR заголовками (>5%), script outline (hook 15s + 3 main points + CTA), thumbnail concept description (для AI генерации в Midjourney/SD), tags для SEO, description с timestamps, hooks для Shorts/TikTok версия. Все идеи проверяются на оригинальность (не дубликаты top-100 в нише). Если ниша oversaturated (>1M каналов) — рекомендует sub-niche. Markdown контент-план на 2 недели.",
    },
    {
        "id": "A2_saas_micro_ideas",
        "task": "Скомпилируй промпт для агента генерации micro-SaaS идей с AI. Принимает: бюджет ($0-$10k), skills (frontend/backend/ML/design/marketing уровни 1-5), time available (hours/week). Генерирует 5 идей: для каждой — problem statement, target user (ICP), solution outline, tech stack (предпочтение NoCode: Bubble/Make/Zapier при low skills; Next.js+Supabase при high), MVP scope (2 недели), monetization (free tier + paid,定价), go-to-market (ProductHunt/Twitter/Reddit/HN), competition analysis (похожие продукты, gap), estimated MRR через 6 месяцев (conservative/realistic/optimistic с обоснованием). Все числа → источники (similar SaaS на IndieHackers, Gumroad). Markdown с таблицами.",
    },
    {
        "id": "A3_freelance_ai_augmented",
        "task": "Скомпилируй промпт для агента-помощника freelance writer/designer/developer с AI augmentation. Принимает: текущие skills, часовая ставка, желаемый доход ($/month). Анализирует: какие фриланс-задачи можно 10x ускорить с AI (writing с GPT, design с Midjourney, code с Copilot). Предлагает: 3 ниши где AI даёт competitive advantage, optimized workflow для каждой (вход → AI-шаги → human review → deliverable), pricing strategy (per-project vs retainer vs equity), 5 платформ для старта (Upwork/Fiverr/Contra/Toptal/индивидуально). Включает: realistic timeline до первого клиента, risk mitigation (AI hallucinations, IP issues, client expectations). Markdown план действий на 90 дней с weekly milestones.",
    },
]


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"completed": {}, "failed": {}}


def save_state(state):
    state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def load_cache():
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {}


def save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


class RateLimiter:
    def __init__(self):
        self.min_delay = 2.0
        self.max_delay = 120.0
        self.current_delay = self.min_delay
        self.success = 0
        self.fail = 0

    def on_success(self):
        self.success += 1
        self.fail = 0
        if self.success >= 3:
            self.current_delay = max(self.min_delay, self.current_delay * 0.7)

    def on_rate_limit(self):
        self.fail += 1
        self.success = 0
        factor = 2 ** min(self.fail, 5)
        self.current_delay = min(self.max_delay, self.min_delay * factor)

    def wait(self):
        jitter = random.uniform(0.8, 1.2)
        time.sleep(self.current_delay * jitter)


def call_zai(system_prompt, user_prompt, max_retries=8):
    limiter = RateLimiter()
    last_error = None
    for attempt in range(max_retries):
        try:
            limiter.wait()
            tmp_out = "/tmp/_web_inv_out.json"
            cmd = ["z-ai", "chat", "-s", system_prompt, "-p", user_prompt, "-o", tmp_out]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0 and os.path.exists(tmp_out):
                data = json.loads(Path(tmp_out).read_text())
                content = data.get("choices", [{}])[0].get("message", {}).get("content") or data.get("content")
                if content and len(content) > 50:
                    limiter.on_success()
                    return {"success": True, "content": content, "attempts": attempt + 1}
                last_error = "empty content"
            else:
                stderr = result.stderr or ""
                last_error = stderr[:200]
                if "429" in stderr or "rate" in stderr.lower() or "Too Many" in stderr:
                    limiter.on_rate_limit()
                    print(f"  ⚠️ rate-limit attempt {attempt+1}: wait {limiter.current_delay:.1f}s")
                elif "context deadline" in stderr or "timeout" in stderr.lower():
                    limiter.on_rate_limit()
                    print(f"  ⚠️ timeout attempt {attempt+1}: wait {limiter.current_delay:.1f}s")
                else:
                    time.sleep(5)
        except subprocess.TimeoutExpired:
            last_error = "subprocess timeout"
            limiter.on_rate_limit()
        except Exception as e:
            last_error = str(e)
            time.sleep(5)
    return {"success": False, "error": last_error, "attempts": max_retries}


def cache_key(system_prompt, user_prompt):
    h = hashlib.sha256()
    h.update(system_prompt.encode())
    h.update(b"|||")
    h.update(user_prompt.encode())
    return h.hexdigest()[:32]


def run_tests():
    state = load_state()
    cache = load_cache()

    print("=" * 80)
    print(f"ТЕСТ {VERSION} — Websites/Investing/AI-Money (9 задач)")
    print(f"Готово: {len(state['completed'])}/9")
    print("=" * 80)

    results = []
    for test in TESTS:
        test_id = test["id"]

        if test_id in state["completed"]:
            cached_file = OUT_DIR / f"{test_id}.md"
            if cached_file.exists():
                content = cached_file.read_text()
                print(f"\n✓ {test_id} — SKIP (cached)")
                results.append({"id": test_id, "task": test["task"], "compiled": content, "skipped": True})
                continue

        print(f"\n▶ {test_id}")
        print(f"  {test['task'][:100]}...")

        key = cache_key(META_PROMPT, test["task"])
        if key in cache:
            content = cache[key]
            print(f"  → CACHE HIT")
        else:
            result = call_zai(META_PROMPT, test["task"])
            if result["success"]:
                content = result["content"]
                cache[key] = content
                save_cache(cache)
                print(f"  ✓ {len(content)} chars (attempts: {result['attempts']})")
            else:
                print(f"  ✗ FAILED: {result['error']}")
                state["failed"][test_id] = {"error": result["error"]}
                save_state(state)
                results.append({"id": test_id, "task": test["task"], "compiled": f"[ERROR: {result['error']}]", "failed": True})
                continue

        (OUT_DIR / f"{test_id}.md").write_text(content)
        state["completed"][test_id] = {"content_length": len(content), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
        save_state(state)
        results.append({"id": test_id, "task": test["task"], "compiled": content})

    (OUT_DIR / "_all_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))

    print("\n" + "=" * 80)
    print(f"ИТОГ: {sum(1 for r in results if not r.get('failed'))}/{len(TESTS)} успешно")
    print(f"Файлы: {OUT_DIR}")
    return results


if __name__ == "__main__":
    run_tests()
