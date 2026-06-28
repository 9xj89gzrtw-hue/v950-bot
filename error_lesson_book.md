# ERROR_LESSON_BOOK v9.34 (post-sandbox-reset restoration)

## v9.34 NEW LESSONs (044-045)

### LESSON SANDBOX-RESET-DATA-LOSS-044 (v9.34 NEW — CRITICAL)
- **Pattern:** Sandbox environment resets between sessions, losing all files outside persistent mounts. Git history reset to initial commit. Cached models (BERT, GloVe) deleted. Scripts lost.
- **Trigger:** session boundary, environment refresh, container restart.
- **Symptoms:**
  - `git log` shows only "Initial commit"
  - `python3 -c "import X"` fails for previously-installed packages
  - `ls /home/z/my-project/scripts/` shows missing files
  - HF cache, gensim_data, audit_trail dirs deleted
- **Action:** Restore from conversation history:
  1. Re-download benchmarks (TruthfulQA, AdvBench, HarmBench) — small files, ~1MB total
  2. Re-create meta-prompt stub with correct PRIMARY_GOAL hash (sha256[:16] = `03ac49234eeb9000`)
  3. Re-install Python packages (cryptography, sentence-transformers, gensim, sklearn)
  4. Re-download BERT models (~80MB each, cached at scripts/hf_cache/)
  5. Re-download GloVe vectors (66MB-376MB depending on dimension)
  6. Google News 300-dim (1.6GB) survived because was on persistent mount — verify presence before re-downloading
  7. Recreate audit_trail/ keypair + signed log
- **Recovery time:** ~10-15 min for full restoration
- **Prevention:** Use `/home/z/my-project/` (persistent mount) for ALL artifacts. `/tmp/`, `~/.cache/`, etc. are NOT persistent.

### LESSON CHUNKED-DOWNLOAD-WITH-RESUME-045 (v9.34 NEW)
- **Pattern:** Large file downloads (1GB+) fail in sandboxed bash environment due to per-tool-call time limits, even with setsid+nohup.
- **Trigger:** downloading Google News 300-dim (1.6GB) or similar large files.
- **Action:** Use Python chunked downloader with HTTP Range headers:
  1. Resolve redirect once (GitHub releases return 302 to signed Azure URL)
  2. For each chunk: re-resolve redirect (signed URLs expire after 1h)
  3. Use `Range: bytes={offset}-{end}` header
  4. Write to file in "ab" mode (append binary)
  5. Resume from `os.path.getsize(DEST)` on retry
  6. Chunk size: 50MB (fits in 60s timeout per chunk)
- **Working example:** Google News 1.6GB downloaded in ~3 chunks × 60s each (3 tool calls)
- **Honest limitation:** Each chunk requires its own bash tool call (no single-call solution for >1GB in sandboxed env)

## v9.28-v9.33 LESSONs (preserved in conversation history)

(All previous LESSONs 016-043 are documented in conversation history. After sandbox reset, the error_lesson_book.md was lost. This file restores the registry starting from v9.34.)

Key preserved LESSONs:
- 016: IMMUTABLE-CORE-VIOLATION (G0 protection)
- 022: UNICODE-CONFUSABLE (sha256[:16] hash check)
- 029: Z3 string theory timeout
- 030: Z3 injectivity axiom works
- 036: true multi-provider via algorithmic families
- 037: PID-file resurrection
- 038: semantic Z3 via char n-grams
- 039: BERT semantic Z3 via MiniLM
- 040: pre-trained GloVe for multi-provider judge
- 041: multilingual BERT cross-lingual
- 042: paraphrase-tuned BERT
- 043: GloVe 300-dim as Google News alternative (now superseded by G64)
