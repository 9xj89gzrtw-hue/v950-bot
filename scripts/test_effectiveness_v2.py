#!/usr/bin/env python3
"""
Эффективность тест v2: использует MultiLLM (z-ai + Pollinations fallback).
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, '/home/z/my-project/scripts')
from multi_llm import MultiLLM

VERSION = sys.argv[1] if len(sys.argv) > 1 else "v9.87-MULTI-LLM"
REPO = Path("/home/z/my-project/repo")
PROMPT_FILE = REPO / f"meta-prompt-{VERSION}.md"
META_PROMPT = PROMPT_FILE.read_text()

OUT_DIR = Path(f"/home/z/my-project/download/effectiveness_{VERSION.replace('.', '_')}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = OUT_DIR / "_state.json"

META_TASKS = [
    {
        "id": "M1_website_prompt",
        "task": "Скомпилируй промпт, после которого ЛЮБАЯ LLM (Claude/GPT/Gemini) с ПЕРВОЙ попытки создаёт ЛУЧШИЙ В МИРЕ сайт для заданного продукта. Промпт должен заставить модель: сразу выдать production-ready код (Next.js 14 + Tailwind + shadcn/ui), без итераций; hero section с уникальным UVP; идеальную визуальную иерархию; accessibility WCAG 2.2 AAA (не AA); SEO с schema.org и JSON-LD; performance LCP <1.5s; conversion-optimized CTA; social proof placement основанный на behavioral research; mobile-first с touch targets ≥48px. Промпт должен работать в любом сервисе (v0/bolt/Cursor/Lovable/Replit). На выходе — код, который можно сразу deploy на Vercel.",
    },
    {
        "id": "M2_investing_prompt",
        "task": "Скомпилируй промпт, после которого ЛЮБАЯ LLM с ПЕРВОЙ попытки анализирует инвестиционный портфель ЛУЧШЕ ЛЮБОГО ЧЕЛОВЕКА в мире и выдаёт рекомендации, которые ДЕЙСТВИТЕЛЬНО УВЕЛИЧАТ деньги пользователя. Промпт должен заставить модель: получить все нужные данные о портфеле (тикеры, количества, cost basis, дата покупки); посчитать drift от target allocation; выявить tax-loss harvesting возможности с wash sale rule; проанализировать correlation между позициями; учесть macro environment (Fed rate, VIX, yield curve); сравнить с benchmark (S&P 500, 60/40 portfolio); дать конкретные buy/sell ордера с обоснованием; backtest стратегию на 2008/2020/crash сценариях; SEC/FINRA compliance disclaimers. На выходе — JSON ready для broker API integration.",
    },
    {
        "id": "M3_aimoney_prompt",
        "task": "Скомпилируй промпт, после которого ЛЮБАЯ LLM с ПЕРВОЙ попытки помогает пользователю ДЕЙСТВИТЕЛЬНО ОЧЕНЬ ЛЕГКО ЗАРАБОТАТЬ ОЧЕНЬ МНОГО ДЕНЕГ с AI. Промпт должен заставить модель: проанализировать skills пользователя (5 минут интервью); выбрать 1 ЛУЧШУЮ идею из топ-10 verified AI money-making streams 2025 (faceless YouTube, AI SaaS, freelance AI augmentation, content repurposing, AI art commissions, automation agency, AI consulting, prompt engineering, AI tutoring, data labeling); дать step-by-step план с конкретными tool choices; указать exact pricing strategy (не 'charge what you're worth', а 'price at $X based on similar offers on Gumroad'); рассчитать реалистичный timeline (НЕ 'get rich quick', а 'first $100 в week 1, $1k MRR в month 3'); предупредить о ТОП-3 рисках; дать exact first action на сегодня. На выходе — actionable 30-day plan с daily milestones.",
    },
]

USER_TASKS = [
    {
        "id": "M1_website_prompt",
        "task": "Создай landing page для моего SaaS продукта: 'TaskFlow' — AI-powered project management tool для remote-команд 5-50 человек. Целевая аудитория: tech leads и project managers в startups. Ключевые фичи: AI task prioritization, async standups, integration с Slack/Linear/Notion. Цена: $9/user/month (Pro), $19/user/month (Enterprise). Я хочу, чтобы после этого промпта я мог сразу вставить код в v0.dev или Cursor и получить лучший в мире landing page.",
    },
    {
        "id": "M2_investing_prompt",
        "task": "Вот мой портфель: 200 AAPL @ $150 (куплено 2023-01-15), 150 MSFT @ $280 (2023-03-20), 50 NVDA @ $200 (2022-11-10), 100 GOOGL @ $120 (2023-06-05), 30 TSLA @ $180 (2024-02-01), 500 VTI @ $230 (2023-09-15), 200 BND @ $80 (2023-04-01). Target allocation: 70% stocks, 20% bonds, 10% international. Я в US, долгосрочный инвестор (10+ лет), 35 лет, риск-tolerance moderate. Дай мне ЛУЧШИЕ В МИРЕ рекомендации, которые ДЕЙСТВИТЕЛЬНО увеличат мои деньги в следующие 12 месяцев.",
    },
    {
        "id": "M3_aimoney_prompt",
        "task": "Я хочу зарабатывать деньги с AI. У меня: skills — frontend dev (React, 7/10), basic Python (4/10), elementary design (3/10), немного маркетинга (5/10). Время: 15 часов в неделю. Бюджет: $500 на старте. Цель: $5k/month через 6 месяцев. Я хочу, чтобы после этого промпта я знал ТОЧНО что делать начиная с сегодняшнего вечера, и это РЕАЛЬНО принесло мне деньги (не 'попробуй 10 идей', а 1 конкретная идея с пошаговым планом).",
    },
]


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"completed": {}, "failed": {}}


def save_state(state):
    state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def run_pipeline():
    state = load_state()
    llm = MultiLLM(cache_path=Path(f"/home/z/my-project/download/_multi_llm_cache.json"), verbose=True)

    print("=" * 80)
    print(f"ЭФФЕКТИВНОСТЬ ТЕСТ v2 {VERSION} (multi-provider)")
    print("=" * 80)

    results = []

    for meta_task, user_task in zip(META_TASKS, USER_TASKS):
        test_id = meta_task["id"]

        # STEP 1: generate domain prompt
        dp_file = OUT_DIR / f"{test_id}_domain_prompt.md"
        if test_id + "_step1" in state.get("completed", {}) and dp_file.exists():
            domain_prompt = dp_file.read_text()
            print(f"\n✓ {test_id} STEP 1 — CACHED")
        else:
            print(f"\n▶ {test_id} STEP 1: meta-prompt → domain prompt")
            r = llm.chat(META_PROMPT, meta_task["task"], max_retries=3)
            if not r["success"]:
                print(f"  ✗ FAILED: {r.get('error')}")
                state["failed"][test_id + "_step1"] = {"error": r.get("error")}
                save_state(state)
                continue
            domain_prompt = r["content"]
            dp_file.write_text(domain_prompt)
            state.setdefault("completed", {})[test_id + "_step1"] = {"length": len(domain_prompt)}
            save_state(state)
            print(f"  ✓ {len(domain_prompt)} chars ({r['provider']})")

        # STEP 2: domain prompt + user task → output
        output_file = OUT_DIR / f"{test_id}_output.md"
        if test_id + "_step2" in state.get("completed", {}) and output_file.exists():
            output = output_file.read_text()
            print(f"  ✓ STEP 2 — CACHED")
        else:
            print(f"  ▶ STEP 2: domain prompt + user task → output")
            r = llm.chat(domain_prompt, user_task["task"], max_retries=3)
            if not r["success"]:
                print(f"  ✗ FAILED: {r.get('error')}")
                state["failed"][test_id + "_step2"] = {"error": r.get("error")}
                save_state(state)
                continue
            output = r["content"]
            output_file.write_text(output)
            state.setdefault("completed", {})[test_id + "_step2"] = {"length": len(output)}
            save_state(state)
            print(f"  ✓ {len(output)} chars ({r['provider']})")

        results.append({
            "id": test_id,
            "meta_task": meta_task["task"],
            "user_task": user_task["task"],
            "domain_prompt": domain_prompt,
            "output": output,
        })

    (OUT_DIR / "_all_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print("\n" + "=" * 80)
    print(f"Готово: {len(results)}/3")
    print(f"Stats: {llm.get_stats()}")
    return results


if __name__ == "__main__":
    run_pipeline()
