#!/usr/bin/env python3
"""
Check model freshness — сравнивает локальные модели с latest на HuggingFace.
Запускать weekly (cron).
"""
import json
import urllib.request
from pathlib import Path
from datetime import datetime

MODELS_DIR = Path("/home/z/my-project/models")
MEMORY_FILE = Path("/home/z/my-project/MEMORY.md")
HF_API = "https://huggingface.co/api/models"

LOCAL_MODELS = {
    "Qwen3.5-4B-Q5_K_M.gguf": {"repo": "unsloth/Qwen3.5-4B-GGUF", "family": "Qwen3.5"},
    "Qwen3-4B-Q5_K_M.gguf": {"repo": "Qwen/Qwen3-4B-GGUF", "family": "Qwen3"},
}


def check_latest(family: str) -> dict:
    """Check HuggingFace for latest models in family."""
    try:
        url = f"{HF_API}?search={family}&sort=createdAt&direction=-1&limit=5"
        req = urllib.request.Request(url, headers={"User-Agent": "ModelFreshness/1.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        return {
            "latest": [{"id": m.get("id", ""), "created": m.get("createdAt", "")[:10]} for m in data[:5]],
            "checked_at": datetime.now().strftime("%Y-%m-%d"),
        }
    except Exception as e:
        return {"error": str(e), "checked_at": datetime.now().strftime("%Y-%m-%d")}


def main():
    print("Model Freshness Check")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()

    families = set(m["family"] for m in LOCAL_MODELS.values())
    results = {}
    for family in families:
        print(f"Checking {family}...")
        results[family] = check_latest(family)
        if "latest" in results[family]:
            for m in results[family]["latest"]:
                print(f"  - {m['id']} ({m['created']})")

    # Update MEMORY.md
    entry = f"\n## Model Checkup {datetime.now().strftime('%Y-%m-%d')}\n"
    for family, data in results.items():
        if "latest" in data:
            entry += f"- {family}: latest={data['latest'][0]['id']} ({data['latest'][0]['created']})\n"

    if MEMORY_FILE.exists():
        content = MEMORY_FILE.read_text()
        MEMORY_FILE.write_text(content + entry)
    else:
        MEMORY_FILE.write_text(f"# MEMORY\n{entry}")

    print(f"\n✓ Updated {MEMORY_FILE}")
    return results


if __name__ == "__main__":
    main()
