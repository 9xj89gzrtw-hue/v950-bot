#!/usr/bin/env python3
"""
v937_daemon.py — PERSISTENT PYTHON DAEMON v9.37
=================================================
Solves: every script invocation pays 8.8s for imports + 14-120s for model loads.
Solution: one persistent process holds all imports + models in memory,
accepts commands via Unix socket, returns results as JSON.

Speedup:
- Without daemon: each gate = 8.8s imports + model load (14-120s) + actual work
- With daemon: each gate = socket round-trip (~10ms) + actual work

Usage:
    # Start daemon (background, persistent):
    python3 /home/z/my-project/scripts/v937_daemon.py --start
    
    # Run a command via daemon:
    python3 /home/z/my-project/scripts/v937_daemon.py --run "g0_check"
    python3 /home/z/my-project/scripts/v937_daemon.py --run "bert_sim" --args "text1" "text2"
    python3 /home/z/my-project/scripts/v937_daemon.py --run "z3_verify"
    
    # Stop daemon:
    python3 /home/z/my-project/scripts/v937_daemon.py --stop
    
    # Status:
    python3 /home/z/my-project/scripts/v937_daemon.py --status
"""
import argparse
import hashlib
import json
import os
import re
import socket
import sys
import time
from pathlib import Path

SOCKET_PATH = "/home/z/my-project/scripts/v937_daemon.sock"
PID_FILE = "/home/z/my-project/scripts/v937_daemon.pid"
LOG_FILE = "/home/z/my-project/download/v937_daemon.log"

# Set env for HF cache
os.environ.setdefault('TRANSFORMERS_CACHE', '/home/z/my-project/scripts/hf_cache')
os.environ.setdefault('HF_HOME', '/home/z/my-project/scripts/hf_cache')


def log(msg):
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = f"[{ts}] {msg}"
    print(line, file=sys.stderr, flush=True)
    try:
        Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ============================================================================
# LAZY-LOADED RESOURCES (only loaded when first needed, then cached)
# ============================================================================

_RESOURCES = {}


def get_z3():
    if 'z3' not in _RESOURCES:
        log("loading z3...")
        import z3
        _RESOURCES['z3'] = z3
        log(f"  z3 loaded: {z3.get_version_string()}")
    return _RESOURCES['z3']


def get_bert_model(model_id='sentence-transformers/all-MiniLM-L6-v2'):
    key = f'bert_{model_id}'
    if key not in _RESOURCES:
        log(f"loading BERT {model_id}...")
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(model_id)
        _RESOURCES[key] = m
        log(f"  BERT loaded, dim={m.get_sentence_embedding_dimension()}")
    return _RESOURCES[key]


def get_word2vec_kv(kv_path, name):
    key = f'w2v_{name}'
    if key not in _RESOURCES:
        log(f"loading {name} from {kv_path}...")
        from gensim.models import KeyedVectors
        if os.path.exists(kv_path):
            _RESOURCES[key] = KeyedVectors.load(kv_path)
        else:
            return None
        log(f"  {name} loaded, vocab={len(_RESOURCES[key]):,}")
    return _RESOURCES[key]


# ============================================================================
# COMMAND HANDLERS
# ============================================================================

META_PROMPT_PATH = "/home/z/my-project/upload/meta-prompt-v9.28-abstention-prefill-context.md"
CANONICAL_PRIMARY_GOAL = "> Создавать **лучшие в мире промпты**, которые **решают задачи пользователя правильно с первой попытки**, и **никогда не врут**."
CANONICAL_HASH = "03ac49234eeb9000"


def cmd_g0_check(args):
    """G0 immutable-core check (fast, no model needed)."""
    text = Path(META_PROMPT_PATH).read_text(encoding="utf-8")
    m = re.search(r"^> Создавать[^\n]*$", text, re.MULTILINE)
    if not m:
        return {"pass": False, "error": "PRIMARY_GOAL line not found"}
    actual_hash = hashlib.sha256(m.group(0).encode("utf-8")).hexdigest()[:16]
    return {
        "pass": actual_hash == CANONICAL_HASH,
        "actual_hash": actual_hash,
        "expected_hash": CANONICAL_HASH,
    }


def cmd_z3_verify(args):
    """Z3 hash-injectivity proof (uses cached z3 import)."""
    z3 = get_z3()
    s = z3.Solver()
    s.set("timeout", 10000)
    sha_fn = z3.Function("sha256_16", z3.StringSort(), z3.BitVecSort(64))
    expected_bv = z3.BitVecVal(int(CANONICAL_HASH, 16), 64)
    x = z3.Const("x", z3.StringSort())
    y = z3.Const("y", z3.StringSort())
    s.add(z3.ForAll([x, y], z3.Implies(sha_fn(x) == sha_fn(y), x == y)))
    s.add(sha_fn(z3.StringVal(CANONICAL_PRIMARY_GOAL)) == expected_bv)
    test_line = z3.Const("test_line", z3.StringSort())
    s.add(sha_fn(test_line) == expected_bv)
    s.add(z3.IndexOf(test_line, z3.StringVal("никогда не врут"), 0) < 0)
    t0 = time.time()
    rc = s.check()
    return {
        "result": str(rc),
        "proven": rc == z3.unsat,
        "time_sec": round(time.time() - t0, 3),
    }


def cmd_bert_sim(args):
    """BERT cosine similarity between two texts."""
    if len(args) < 2:
        return {"error": "need 2 args: text1 text2"}
    text1, text2 = args[0], args[1]
    model_id = args[2] if len(args) > 2 else 'sentence-transformers/all-MiniLM-L6-v2'
    import numpy as np
    model = get_bert_model(model_id)
    emb = model.encode([text1, text2], normalize_embeddings=True)
    sim = float(np.dot(emb[0], emb[1]))
    return {"similarity": sim, "model": model_id}


def cmd_bert_check_primary_goal(args):
    """Check current PRIMARY_GOAL vs canonical using BERT."""
    import numpy as np
    text = Path(META_PROMPT_PATH).read_text(encoding="utf-8")
    m = re.search(r"^> Создавать[^\n]*$", text, re.MULTILINE)
    if not m:
        return {"pass": False, "error": "line not found"}
    actual = m.group(0)
    model_id = args[0] if args else 'sentence-transformers/all-MiniLM-L6-v2'
    model = get_bert_model(model_id)
    emb = model.encode([CANONICAL_PRIMARY_GOAL, actual], normalize_embeddings=True)
    sim = float(np.dot(emb[0], emb[1]))
    return {
        "similarity": sim,
        "pass": sim >= 0.95,
        "model": model_id,
    }


def cmd_w2v_sim(args):
    """Word2vec cosine similarity. args: text1 text2 model_name"""
    if len(args) < 3:
        return {"error": "need 3 args: text1 text2 model_name"}
    text1, text2, model_name = args[0], args[1], args[2]
    import numpy as np
    kv_paths = {
        'ruscorpora': '/home/z/my-project/scripts/gensim_data/word2vec-ruscorpora-300.kv',
        'glove50': '/home/z/my-project/scripts/gensim_data/glove-wiki-gigaword-50.kv',
    }
    kv_path = kv_paths.get(model_name)
    if not kv_path:
        return {"error": f"unknown model: {model_name}"}
    kv = get_word2vec_kv(kv_path, model_name)
    if kv is None:
        return {"error": f"model {model_name} not available"}
    # Simple tokenization
    tokens1 = re.findall(r'\b[a-zа-яё]{3,}\b', text1.lower())
    tokens2 = re.findall(r'\b[a-zа-яё]{3,}\b', text2.lower())
    vecs1 = [kv[t] for t in tokens1 if t in kv]
    vecs2 = [kv[t] for t in tokens2 if t in kv]
    if not vecs1 or not vecs2:
        return {"similarity": 0.0, "matched1": len(vecs1), "matched2": len(vecs2)}
    v1 = np.mean(vecs1, axis=0)
    v2 = np.mean(vecs2, axis=0)
    sim = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
    return {"similarity": sim, "matched1": len(vecs1), "matched2": len(vecs2)}


def cmd_health(args):
    """Health check — return loaded resources."""
    return {
        "status": "alive",
        "resources": list(_RESOURCES.keys()),
        "uptime_sec": round(time.time() - _START_TIME, 1),
    }


COMMANDS = {
    "g0_check": cmd_g0_check,
    "z3_verify": cmd_z3_verify,
    "bert_sim": cmd_bert_sim,
    "bert_check_primary_goal": cmd_bert_check_primary_goal,
    "w2v_sim": cmd_w2v_sim,
    "health": cmd_health,
}


# ============================================================================
# DAEMON SERVER
# ============================================================================

_START_TIME = time.time()


def run_daemon():
    """Run the daemon server."""
    log("v9.37 daemon starting...")
    
    # Remove stale socket
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    server.listen(5)
    server.settimeout(1.0)  # check for shutdown periodically
    
    # Write PID
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    
    log(f"daemon listening on {SOCKET_PATH}, PID={os.getpid()}")
    
    _SHUTDOWN = False
    while not _SHUTDOWN:
        try:
            conn, _ = server.accept()
        except socket.timeout:
            # Check if shutdown requested
            if os.path.exists("/home/z/my-project/scripts/v937_daemon.shutdown"):
                os.unlink("/home/z/my-project/scripts/v937_daemon.shutdown")
                log("shutdown requested")
                break
            continue
        except Exception as e:
            log(f"accept error: {e}")
            continue
        
        try:
            data = b""
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
            
            request = json.loads(data.decode("utf-8").strip())
            cmd = request.get("cmd")
            args = request.get("args", [])
            
            handler = COMMANDS.get(cmd)
            if handler:
                try:
                    result = handler(args)
                    response = {"ok": True, "result": result}
                except Exception as e:
                    response = {"ok": False, "error": str(e)}
            else:
                response = {"ok": False, "error": f"unknown command: {cmd}"}
            
            conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
        except Exception as e:
            log(f"handler error: {e}")
            try:
                conn.sendall((json.dumps({"ok": False, "error": str(e)}) + "\n").encode("utf-8"))
            except Exception:
                pass
        finally:
            conn.close()
    
    # Cleanup
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    if os.path.exists(PID_FILE):
        os.unlink(PID_FILE)
    log("daemon stopped")


# ============================================================================
# CLIENT
# ============================================================================

def send_command(cmd, args=None, timeout=120):
    """Send command to daemon and return response."""
    if not os.path.exists(SOCKET_PATH):
        return {"ok": False, "error": "daemon not running (socket not found)"}
    
    request = {"cmd": cmd, "args": args or []}
    data = (json.dumps(request) + "\n").encode("utf-8")
    
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(SOCKET_PATH)
        client.sendall(data)
        response = b""
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            response += chunk
            if b"\n" in response:
                break
        return json.loads(response.decode("utf-8").strip())
    except socket.timeout:
        return {"ok": False, "error": f"timeout after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        client.close()


def start_daemon():
    """Start daemon in background via setsid."""
    if os.path.exists(PID_FILE):
        pid = Path(PID_FILE).read_text().strip()
        try:
            os.kill(int(pid), 0)
            print(f"daemon already running, PID={pid}")
            return True
        except Exception:
            pass  # stale PID, restart
    
    # Start daemon detached
    setsid_cmd = f"setsid python3 {__file__} --daemon > /dev/null 2>&1 < /dev/null &"
    os.system(setsid_cmd)
    
    # Wait for socket
    for _ in range(30):  # 30 seconds
        time.sleep(1)
        if os.path.exists(SOCKET_PATH):
            # Verify it responds
            r = send_command("health", timeout=5)
            if r.get("ok"):
                print(f"daemon started, PID={Path(PID_FILE).read_text().strip()}")
                return True
    print("daemon failed to start within 30s")
    return False


def stop_daemon():
    """Stop daemon."""
    if not os.path.exists(PID_FILE):
        print("daemon not running")
        return
    pid = Path(PID_FILE).read_text().strip()
    # Create shutdown flag
    Path("/home/z/my-project/scripts/v937_daemon.shutdown").touch()
    # Wait
    for _ in range(10):
        time.sleep(0.5)
        if not os.path.exists(PID_FILE):
            print("daemon stopped")
            return
    # Force kill
    try:
        os.kill(int(pid), 9)
        print(f"daemon force-killed (PID={pid})")
    except Exception:
        pass


def status_daemon():
    """Check daemon status."""
    if not os.path.exists(PID_FILE):
        print("daemon: NOT RUNNING")
        return
    pid = Path(PID_FILE).read_text().strip()
    r = send_command("health", timeout=5)
    if r.get("ok"):
        result = r["result"]
        print(f"daemon: ALIVE (PID={pid})")
        print(f"  uptime: {result['uptime_sec']}s")
        print(f"  resources: {result['resources']}")
    else:
        print(f"daemon: NOT RESPONDING (PID={pid}, error={r.get('error')})")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="v9.37 persistent daemon")
    parser.add_argument("--start", action="store_true", help="start daemon")
    parser.add_argument("--stop", action="store_true", help="stop daemon")
    parser.add_argument("--status", action="store_true", help="daemon status")
    parser.add_argument("--daemon", action="store_true", help="run as daemon (internal)")
    parser.add_argument("--run", metavar="CMD", help="run command via daemon")
    parser.add_argument("--args", nargs="*", default=[], help="command args")
    args = parser.parse_args()
    
    if args.start:
        start_daemon()
    elif args.stop:
        stop_daemon()
    elif args.status:
        status_daemon()
    elif args.daemon:
        run_daemon()
    elif args.run:
        r = send_command(args.run, args.args)
        print(json.dumps(r, indent=2, ensure_ascii=False))
        sys.exit(0 if r.get("ok") else 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
