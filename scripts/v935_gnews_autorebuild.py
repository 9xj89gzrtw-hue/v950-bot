#!/usr/bin/env python3
"""
v935_gnews_autorebuild.py — G65 GOOGLE-NEWS-AUTO-REBUILD v9.35
================================================================
Auto-rebuild Google News .kv cache from .gz on demand.

Solves v9.34 limitation: G63/G64 used .kv cache that could be deleted to save disk.
If .kv missing but .gz present, auto-rebuild .kv (~35s) and cache for future use.

Strategy:
1. Check if .kv exists → load directly (fast, ~1s)
2. If .kv missing but .gz exists → load .gz, save .kv cache, return
3. If both missing → call download_google_news.py to fetch .gz, then rebuild .kv

This gate is also a STANDALONE Google News loader that other gates can import:
    from v935_gnews_autorebuild import get_google_news_kv
    kv = get_google_news_kv()  # always returns valid KeyedVectors
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

GN_GZ_PATH = "/home/z/my-project/scripts/gensim_data/word2vec-google-news-300/word2vec-google-news-300.gz"
GN_KV_PATH = "/home/z/my-project/scripts/gensim_data/word2vec-google-news-300.kv"
GN_KV_VECTORS_PATH = GN_KV_PATH + ".vectors.npy"
DOWNLOAD_SCRIPT = "/home/z/my-project/scripts/download_google_news.py"

_GN_KV = None


def sha8(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


def get_google_news_kv(force_rebuild=False):
    """Get Google News KeyedVectors, auto-rebuilding .kv from .gz if needed.
    
    Args:
        force_rebuild: if True, delete .kv and rebuild from .gz
    
    Returns:
        gensim KeyedVectors (3M vocab, 300-dim)
    """
    global _GN_KV
    if _GN_KV is not None and not force_rebuild:
        return _GN_KV

    from gensim.models import KeyedVectors

    # Strategy 1: .kv cache exists → load fast
    if not force_rebuild and os.path.exists(GN_KV_PATH) and os.path.exists(GN_KV_VECTORS_PATH):
        t0 = time.time()
        _GN_KV = KeyedVectors.load(GN_KV_PATH)
        load_time = time.time() - t0
        print(f"  [G65] loaded .kv cache in {load_time:.1f}s (vocab={len(_GN_KV):,})", file=sys.stderr)
        return _GN_KV

    # Strategy 2: .gz exists → load directly (don't cache .kv, it's 3.6GB)
    # On-disk .kv cache is too large for sandbox; we trade load time for disk space.
    if os.path.exists(GN_GZ_PATH):
        gz_size = os.path.getsize(GN_GZ_PATH)
        if gz_size < 1743563840:  # incomplete
            print(f"  [G65] .gz incomplete ({gz_size} bytes), launching download...", file=sys.stderr)
            subprocess.run([sys.executable, DOWNLOAD_SCRIPT], check=True)
        print(f"  [G65] loading from .gz directly (~35s, no .kv cache to save disk)...", file=sys.stderr)
        t0 = time.time()
        _GN_KV = KeyedVectors.load_word2vec_format(GN_GZ_PATH, binary=True)
        load_time = time.time() - t0
        print(f"  [G65] loaded in {load_time:.1f}s (vocab={len(_GN_KV):,})", file=sys.stderr)
        # NOTE: deliberately NOT saving .kv cache — it's 3.6GB, too large for sandbox disk
        # If disk has >5GB free, can save; otherwise skip
        import shutil
        # Use parent dir for disk_usage check (file may not exist yet)
        disk_check_path = os.path.dirname(GN_KV_PATH) or "/"
        disk_free = shutil.disk_usage(disk_check_path).free
        if disk_free > 5_000_000_000:  # 5GB free
            print(f"  [G65] saving .kv cache (disk has {disk_free//1e9:.1f}GB free)...", file=sys.stderr)
            _GN_KV.save(GN_KV_PATH)
        else:
            print(f"  [G65] skipping .kv cache (disk has only {disk_free//1e9:.1f}GB free, .kv needs 3.6GB)", file=sys.stderr)
        return _GN_KV

    # Strategy 3: both missing → download .gz first
    print(f"  [G65] .gz missing, launching download...", file=sys.stderr)
    subprocess.run([sys.executable, DOWNLOAD_SCRIPT], check=True)
    # Now .gz should exist → recurse
    return get_google_news_kv(force_rebuild=False)


def check_google_news_available():
    """Check if Google News is available (either .kv or .gz)."""
    has_kv = os.path.exists(GN_KV_PATH) and os.path.exists(GN_KV_VECTORS_PATH)
    has_gz = os.path.exists(GN_GZ_PATH) and os.path.getsize(GN_GZ_PATH) >= 1743563840
    return {
        "has_kv_cache": has_kv,
        "has_gz_complete": has_gz,
        "kv_path": GN_KV_PATH,
        "gz_path": GN_GZ_PATH,
        "gz_size_bytes": os.path.getsize(GN_GZ_PATH) if os.path.exists(GN_GZ_PATH) else 0,
        "available": has_kv or has_gz,
        "auto_rebuild_possible": has_gz,
    }


def main():
    print("=" * 70)
    print("G65 GOOGLE-NEWS-AUTO-REBUILD v9.35")
    print("=" * 70)
    print()

    # Step 1: Check availability
    print("[1/3] Availability check:")
    avail = check_google_news_available()
    print(f"     has .kv cache: {avail['has_kv_cache']}")
    print(f"     has .gz complete: {avail['has_gz_complete']}")
    print(f"     .gz size: {avail['gz_size_bytes']:,} bytes")
    print(f"     auto-rebuild possible: {avail['auto_rebuild_possible']}")
    print()

    if not avail["available"]:
        print("[2/3] Both .kv and .gz missing — launching download...")
        subprocess.run([sys.executable, DOWNLOAD_SCRIPT])
        # Re-check
        avail = check_google_news_available()

    # Step 2: Load (auto-rebuild if needed)
    print("[2/3] Loading Google News (auto-rebuild if .kv missing):")
    t0 = time.time()
    kv = get_google_news_kv()
    load_time = time.time() - t0
    print(f"     loaded in {load_time:.1f}s")
    print(f"     vocab: {len(kv):,}")
    print(f"     dim: {kv.vector_size}")
    print()

    # Step 3: Verify functionality
    print("[3/3] Functionality test:")
    sim_kq = kv.similarity('king', 'queen')
    sim_kb = kv.similarity('king', 'banana')
    sim_kc = kv.similarity('king', 'crown')
    print(f"     sim(king, queen) = {sim_kq:.4f}  (expected ~0.65)")
    print(f"     sim(king, banana) = {sim_kb:.4f}  (expected ~0.14)")
    print(f"     sim(king, crown) = {sim_kc:.4f}  (expected ~0.32)")
    
    functional = bool(sim_kq > 0.5 and sim_kb < 0.3 and sim_kq > sim_kb)
    print(f"     functional: {'YES' if functional else 'NO'}")
    print()

    print("=" * 70)
    print("VERDICT")
    print("=" * 70)
    print(f"Available: {'YES' if avail['available'] else 'NO'}")
    print(f"Auto-rebuild: {'POSSIBLE' if avail['auto_rebuild_possible'] else 'NOT POSSIBLE'}")
    print(f"Functional: {'YES' if functional else 'NO'}")
    print()
    print("This gate ensures Google News 300-dim is always available to G63/G64,")
    print("even if .kv cache was deleted to save disk space.")
    print("=" * 70)

    out = Path("/home/z/my-project/download/benchmarks/gnews_autorebuild_v935.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "test": "G65-google-news-auto-rebuild",
        "version": "v9.35",
        "availability": avail,
        "load_time_sec": round(load_time, 1),
        "vocab_size": len(kv),
        "vector_dim": kv.vector_size,
        "functionality": {
            "sim_king_queen": round(float(sim_kq), 4),
            "sim_king_banana": round(float(sim_kb), 4),
            "sim_king_crown": round(float(sim_kc), 4),
            "functional": functional,
        },
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"JSON: {out}")


if __name__ == "__main__":
    main()
