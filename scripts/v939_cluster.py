#!/usr/bin/env python3
"""
v939_cluster.py — DAEMON CLUSTER v9.39
========================================
Multi-worker daemon cluster for parallel LLM calls.

Architecture:
- 1 master daemon (v937_daemon.py on default socket) — handles gates (Z3, BERT, w2v)
- N worker daemons (on worker sockets) — handle LLM calls in parallel
- Load balancer distributes LLM requests across workers

Workers share the same codebase but run as separate processes on different
Unix sockets, enabling true parallelism for LLM calls (which are I/O bound).

Usage:
    python3 v939_cluster.py --start --workers 3   # start 3-worker cluster
    python3 v939_cluster.py --status               # cluster status
    python3 v939_cluster.py --stop                  # stop all workers
    python3 v939_cluster.py --run llm_chat --args "Hello"  # balanced call
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

MASTER_SOCKET = "/home/z/my-project/scripts/v937_daemon.sock"
WORKER_SOCKET_PREFIX = "/home/z/my-project/scripts/v939_worker"
PID_DIR = "/home/z/my-project/scripts"
DEFAULT_WORKERS = 3


def get_worker_sockets(n):
    """Get list of worker socket paths."""
    return [f"{WORKER_SOCKET_PREFIX}_{i}.sock" for i in range(n)]


def get_worker_pids():
    """Get list of running worker PIDs."""
    pids = []
    for f in Path(PID_DIR).glob("v939_worker_*.pid"):
        try:
            pid = int(f.read_text().strip())
            if _pid_alive(pid):
                pids.append((str(f), pid))
        except Exception:
            pass
    return pids


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def start_worker(worker_id, socket_path):
    """Start a single worker daemon."""
    pid_file = f"{PID_DIR}/v939_worker_{worker_id}.pid"
    
    # Check if already running
    if os.path.exists(pid_file):
        pid = int(Path(pid_file).read_text().strip())
        if _pid_alive(pid):
            print(f"  worker {worker_id} already running (PID={pid})")
            return pid
    
    # Start worker — it's just v937_daemon.py with custom socket path
    # We use env var to override socket path
    env = os.environ.copy()
    env["V937_SOCKET_PATH"] = socket_path
    env["V937_PID_FILE"] = pid_file
    
    # Write a small wrapper that overrides socket path
    wrapper = f"""
import sys, os
sys.path.insert(0, '/home/z/my-project/scripts')
import v937_daemon
v937_daemon.SOCKET_PATH = '{socket_path}'
v937_daemon.PID_FILE = '{pid_file}'
v937_daemon.run_daemon()
"""
    wrapper_path = f"/tmp/v939_worker_wrapper_{worker_id}.py"
    Path(wrapper_path).write_text(wrapper)
    
    setsid_cmd = f"setsid python3 {wrapper_path} > /dev/null 2>&1 < /dev/null &"
    os.system(setsid_cmd)
    
    # Wait for socket
    for _ in range(30):
        time.sleep(0.5)
        if os.path.exists(socket_path):
            # Verify
            try:
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.settimeout(3)
                client.connect(socket_path)
                client.sendall((json.dumps({"cmd": "health", "args": []}) + "\n").encode())
                resp = b""
                while True:
                    chunk = client.recv(65536)
                    if not chunk or b"\n" in chunk:
                        resp += chunk
                        break
                    resp += chunk
                client.close()
                r = json.loads(resp.decode().strip())
                if r.get("ok"):
                    return int(Path(pid_file).read_text().strip())
            except Exception:
                pass
    
    return None


def start_cluster(n_workers=DEFAULT_WORKERS):
    """Start the daemon cluster."""
    print(f"Starting v9.39 daemon cluster with {n_workers} workers...")
    
    # Ensure master daemon is running
    if not os.path.exists(MASTER_SOCKET):
        print("  starting master daemon...")
        subprocess.run(["python3", "/home/z/my-project/scripts/v937_daemon.py", "--start"], timeout=30)
        time.sleep(3)
    
    # Start workers
    worker_sockets = get_worker_sockets(n_workers)
    started = 0
    for i, sock_path in enumerate(worker_sockets):
        print(f"  starting worker {i}...", end=" ")
        pid = start_worker(i, sock_path)
        if pid:
            print(f"OK (PID={pid}, sock={sock_path})")
            started += 1
        else:
            print("FAIL")
    
    print(f"\nCluster: master + {started}/{n_workers} workers started")
    return started


def stop_cluster():
    """Stop all workers (master stays running)."""
    workers = get_worker_pids()
    if not workers:
        print("No workers running")
        return
    
    for pid_file, pid in workers:
        print(f"  stopping worker PID={pid}...")
        try:
            os.kill(pid, 15)  # SIGTERM
        except Exception:
            pass
        # Cleanup
        Path(pid_file).unlink(missing_ok=True)
    
    # Remove worker sockets
    for sock in Path(PID_DIR).glob("v939_worker_*.sock"):
        sock.unlink(missing_ok=True)
    
    # Remove wrappers
    for w in Path("/tmp").glob("v939_worker_wrapper_*.py"):
        w.unlink(missing_ok=True)
    
    print(f"Stopped {len(workers)} workers")


def cluster_status():
    """Show cluster status."""
    print("=== v9.39 Daemon Cluster Status ===")
    print()
    
    # Master
    if os.path.exists(MASTER_SOCKET):
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(3)
            client.connect(MASTER_SOCKET)
            client.sendall((json.dumps({"cmd": "health", "args": []}) + "\n").encode())
            resp = b""
            while True:
                chunk = client.recv(65536)
                if not chunk or b"\n" in chunk:
                    resp += chunk
                    break
                resp += chunk
            client.close()
            r = json.loads(resp.decode().strip())
            if r.get("ok"):
                result = r["result"]
                print(f"  Master: ALIVE (uptime={result['uptime_sec']}s, resources={len(result['resources'])})")
        except Exception:
            print("  Master: NOT RESPONDING")
    else:
        print("  Master: NOT RUNNING")
    
    # Workers
    workers = get_worker_pids()
    if not workers:
        print("  Workers: none running")
    else:
        for pid_file, pid in workers:
            worker_id = pid_file.split("v939_worker_")[1].split(".pid")[0]
            sock_path = f"{WORKER_SOCKET_PREFIX}_{worker_id}.sock"
            alive = "ALIVE" if os.path.exists(sock_path) else "DEAD"
            print(f"  Worker {worker_id}: {alive} (PID={pid})")
    
    print()


def balanced_llm_call(prompt, system=""):
    """Send LLM call to least-busy worker (round-robin for now)."""
    workers = get_worker_pids()
    if not workers:
        # No workers — use master
        return _send_to_socket(MASTER_SOCKET, "llm_chat", [prompt, system])
    
    # Round-robin: use worker based on current time
    idx = int(time.time()) % len(workers)
    pid_file, pid = workers[idx]
    worker_id = pid_file.split("v939_worker_")[1].split(".pid")[0]
    sock_path = f"{WORKER_SOCKET_PREFIX}_{worker_id}.sock"
    
    return _send_to_socket(sock_path, "llm_chat", [prompt, system])


def _send_to_socket(sock_path, cmd, args, timeout=180):
    """Send command to daemon socket."""
    if not os.path.exists(sock_path):
        return {"ok": False, "error": f"socket not found: {sock_path}"}
    
    request = json.dumps({"cmd": cmd, "args": args}) + "\n"
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(sock_path)
        client.sendall(request.encode())
        resp = b""
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            resp += chunk
            if b"\n" in resp:
                break
        return json.loads(resp.decode().strip())
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--run", metavar="CMD")
    parser.add_argument("--args", nargs="*", default=[])
    args = parser.parse_args()
    
    if args.start:
        start_cluster(args.workers)
    elif args.stop:
        stop_cluster()
    elif args.status:
        cluster_status()
    elif args.run:
        if args.run == "llm_chat":
            r = balanced_llm_call(args.args[0] if args.args else "", args.args[1] if len(args.args) > 1 else "")
            print(json.dumps(r, indent=2, ensure_ascii=False))
        else:
            r = _send_to_socket(MASTER_SOCKET, args.run, args.args)
            print(json.dumps(r, indent=2, ensure_ascii=False))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
