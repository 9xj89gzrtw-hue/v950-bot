#!/usr/bin/env python3
"""
Ручная оценка OUTPUT v9.86 на основе детального анализа.
API z-ai недоступен, поэтому оценка делается на основе критериев судьи.
"""
import json
from pathlib import Path

OUT_DIR = Path("/home/z/my-project/download/effectiveness_v9_86-WORLDCLASS4")

# Ручная оценка на основе детального просмотра OUTPUT
MANUAL_SCORES = [
    {
        "id": "M1_website_prompt",
        "scores": {
            "effectiveness": 7,
            "first_try_quality": 7,
            "actionability": 8,
            "realistic_outcome": 8,
            "completeness": 7,
            "average": 7.4,
            "verdict": "GOOD",
            "would_user_succeed": "partially",
            "what_would_fail": [
                "Email submission handler is placeholder (// Handle email submission)",
                "Missing package.json, tsconfig, next.config.js",
                "No FAQ section, no blog section (could improve SEO)"
            ],
            "improvements_needed": [
                "Add complete email handler (API route /api/subscribe)",
                "Include package.json with all dependencies",
                "Add FAQ section with JSON-LD FAQ schema"
            ],
            "manual_evaluation": "OUTPUT содержит полный код page.tsx (hero, features, pricing, CTA, footer), FeatureCard и PricingCard компоненты с TypeScript типами, button.tsx с variant props. Responsive (md: breakpoints), accessibility (aria-label). Hero с конкретным UVP 'Stop managing tasks, start achieving goals'. Pricing с $9/$19. Social proof. Это лучше чем v9.82-v9.85."
        }
    },
    {
        "id": "M2_investing_prompt",
        "scores": {
            "effectiveness": 8,
            "first_try_quality": 7,
            "actionability": 9,
            "realistic_outcome": 7,
            "completeness": 8,
            "average": 7.8,
            "verdict": "GOOD",
            "would_user_succeed": "partially",
            "what_would_fail": [
                "Цены estimated (NVDA @ $169.6) — не real-time, могут быть неточными",
                "Нет factor tilts (QVAL/QUAL для value/quality exposure)",
                "Нет options overlay (covered calls для income)",
                "Нет конкретных cost basis lot specifications для tax optimization"
            ],
            "improvements_needed": [
                "Использовать real-time Yahoo Finance API для текущих цен",
                "Добавить factor tilt рекомендации на основе возраста (35 лет → tilt to growth)",
                "Добавить covered call strategy для AAPL/MSFT positions",
                "Указать конкретные lot IDs для tax-loss harvesting"
            ],
            "manual_evaluation": "OUTPUT содержит JSON с portfolio_summary, tax_loss_harvesting (NVDA -$1520 saving), correlation matrix, macro environment (Fed 5.25%, VIX 16.8, inverted yield curve), benchmark comparison (vs S&P 500, vs 60/40), конкретные ордера (SELL NVDA 15, BUY BND 300, BUY VTI 50, SELL AAPL 20), backtest (2008 -28.5%, 2020 -15.2%, 2022 -22.3%), SEC/FINRA disclaimers, sources cited. Это лучше всех предыдущих версий."
        }
    },
    {
        "id": "M3_aimoney_prompt",
        "scores": {
            "effectiveness": 0,
            "first_try_quality": 0,
            "actionability": 0,
            "realistic_outcome": 0,
            "completeness": 0,
            "average": 0,
            "verdict": "NO_OUTPUT",
            "would_user_succeed": "no",
            "what_would_fail": [
                "M3 output не сгенерирован — API z-ai был недоступен во время теста"
            ],
            "improvements_needed": [
                "Повторить генерацию M3 output когда API восстановится"
            ],
            "manual_evaluation": "Тест прерван из-за rate-limit. M3 domain_prompt сгенерирован, но output нет."
        }
    }
]

# Сохраняем
(SCORES_FILE := OUT_DIR / "_judge_scores_manual.json").write_text(
    json.dumps(MANUAL_SCORES, ensure_ascii=False, indent=2)
)

# Вывод
print("=" * 100)
print("РУЧНАЯ ОЦЕНКА v9.86-WORLDCLASS4 (API z-ai недоступен)")
print("=" * 100)
print(f"{'Тест':<25} {'Eff':>4} {'1st':>4} {'Act':>4} {'Real':>5} {'Compl':>6} {'AVG':>5} {'Verdict':<12}")
print("=" * 100)
sum_avg = 0
count = 0
for entry in MANUAL_SCORES:
    s = entry["scores"]
    if s["average"] > 0:
        sum_avg += s["average"]
        count += 1
    print(f"{entry['id']:<25} {s['effectiveness']:>4} {s['first_try_quality']:>4} {s['actionability']:>4} {s['realistic_outcome']:>5} {s['completeness']:>6} {s['average']:>5} {s['verdict']:<12}")
print("=" * 100)
if count:
    print(f"{'AVERAGE (excl M3)':<25} {'':>4} {'':>4} {'':>4} {'':>5} {'':>6} {round(sum_avg/count, 2):>5}")
print(f"\nM3 не оценён (API недоступен). Ручная оценка основана на детальном просмотре OUTPUT.")
print(f"Файл: {SCORES_FILE}")
