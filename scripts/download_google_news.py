#!/usr/bin/env python3
"""
download_google_news.py — chunked download with resume for Google News 1.6GB.
Used by bootstrap.sh when Google News file is missing or partial.

Strategy (from LESSON 045):
1. Resolve GitHub release redirect to get signed Azure URL
2. For each 50MB chunk: re-resolve redirect (signed URLs expire after 1h)
3. Use HTTP Range header
4. Append to file in "ab" mode
5. Resume from os.path.getsize(DEST) on retry

Fits in ~3 bash tool calls for full 1.6GB download.
"""
import os
import sys
import time
import urllib.request
import urllib.error

DEST = "/home/z/my-project/scripts/gensim_data/word2vec-google-news-300/word2vec-google-news-300.gz"
URL = "https://github.com/piskvorky/gensim-data/releases/download/word2vec-google-news-300/word2vec-google-news-300.gz"
CHUNK_SIZE = 50 * 1024 * 1024  # 50MB
MAX_TIME_PER_SESSION = 110  # seconds (fits in 2-min bash timeout)


def main():
    os.makedirs(os.path.dirname(DEST), exist_ok=True)

    existing_size = os.path.getsize(DEST) if os.path.exists(DEST) else 0

    # Resolve direct URL
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
        resp = urllib.request.urlopen(req, timeout=30)
        total_size = int(resp.headers.get("Content-Length", 0))
    except Exception as e:
        print(f"FAIL: cannot resolve URL: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Resume from: {existing_size} bytes ({existing_size//1024//1024}MB)")
    print(f"Total size:  {total_size} bytes ({total_size//1024//1024}MB)")

    if existing_size >= total_size:
        print("✓ Already complete!")
        sys.exit(0)

    remaining = total_size - existing_size
    print(f"Remaining:   {remaining} bytes ({remaining//1024//1024}MB)")

    bytes_downloaded = 0
    start_time = time.time()

    with open(DEST, "ab") as f:
        offset = existing_size
        while offset < total_size:
            elapsed = time.time() - start_time
            if elapsed > MAX_TIME_PER_SESSION:
                print(f"\nTime limit reached ({elapsed:.0f}s), saved {bytes_downloaded//1024//1024}MB this session")
                print(f"Re-run bootstrap.sh to continue from {offset//1024//1024}MB")
                sys.exit(0)

            end = min(offset + CHUNK_SIZE - 1, total_size - 1)

            # Re-resolve direct URL (signed URLs expire)
            try:
                req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
                resp = urllib.request.urlopen(req, timeout=30)
                direct_url = resp.url
            except Exception as e:
                print(f"\nRedirect error: {e}, retrying in 2s...")
                time.sleep(2)
                continue

            # Download chunk
            chunk_req = urllib.request.Request(direct_url, headers={
                "User-Agent": "Mozilla/5.0",
                "Range": f"bytes={offset}-{end}",
            })
            try:
                chunk_resp = urllib.request.urlopen(chunk_req, timeout=60)
                chunk_data = chunk_resp.read()
                f.write(chunk_data)
                f.flush()
                offset += len(chunk_data)
                bytes_downloaded += len(chunk_data)

                elapsed = time.time() - start_time
                speed = bytes_downloaded / elapsed / 1024 if elapsed > 0 else 0
                pct = offset * 100 / total_size
                print(f"  {offset//1024//1024}MB / {total_size//1024//1024}MB ({pct:.1f}%) — {speed:.0f}KB/s")
            except urllib.error.HTTPError as e:
                print(f"\nChunk error at offset {offset}: {e}, retrying in 2s...")
                time.sleep(2)
                continue
            except Exception as e:
                print(f"\nError: {e}, retrying in 2s...")
                time.sleep(2)
                continue

    final_size = os.path.getsize(DEST)
    print(f"\n✓ Done! Final: {final_size} bytes ({final_size//1024//1024}MB)")
    if final_size == total_size:
        print("✓ File complete!")
    else:
        print(f"⚠ Still missing {total_size - final_size} bytes (re-run to continue)")
        sys.exit(1)


if __name__ == "__main__":
    main()
