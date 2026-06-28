#!/usr/bin/env python3
"""
v941_cluster_state.py — PERSISTENT CLUSTER STATE v9.41
========================================================
Survives sandbox reset by persisting cluster state to a JSON file.

State tracked:
- Worker sockets + PIDs + health status
- Last-known response times per worker
- Total requests handled per worker
- Cluster start time
- Restart count (how many times cluster recovered from reset)

On bootstrap Layer 10, this script:
1. Reads state file
2. Detects which workers are still alive (PID check)
3. Restarts dead workers
4. Reports recovery to audit trail

Usage:
    python3 v941_cluster_state.py save       # save current state
    python3 v941_cluster_state.py restore    # restore from file
    python3 v941_cluster_state.py status     # show state
    python3 v941_cluster_state.py migrate    # migrate to current PIDs
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/z/my-project/scripts")

STATE_FILE = "/home/z/my-project/scripts/v941_cluster_state.json"
CLUSTER = "/home/z/my-project/scripts/v939_cluster.py"


def _pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def get_current_state():
    """Get current cluster state (live)."""
    import subprocess
    try:
        result = subprocess.run(
            ["python3", CLUSTER, "--status"],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout
    except Exception as e:
        output = str(e)
    
    # Parse workers from output
    workers = []
    for line in output.split("\n"):
        if "Worker " in line and "PID=" in line:
            # "  Worker 0: ALIVE (PID=12345)"
            parts = line.strip().split()
            worker_id = parts[1].rstrip(":")
            status = parts[2]
            pid = parts[3].split("=")[1].rstrip(")")
            workers.append({
                "id": worker_id,
                "pid": int(pid),
                "status": status,
                "alive": _pid_alive(pid),
                "socket": f"/home/z/my-project/scripts/v939_worker_{worker_id}.sock",
            })
    
    master_alive = "Master: ALIVE" in output
    
    return {
        "master": {"alive": master_alive, "socket": "/home/z/my-project/scripts/v937_daemon.sock"},
        "workers": workers,
        "worker_count": len(workers),
        "timestamp": time.time(),
        "iso_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def save_state():
    """Save current cluster state to file."""
    state = get_current_state()
    
    # Merge with previous state (preserve history)
    previous = load_state()
    if previous:
        state["restart_count"] = previous.get("restart_count", 0)
        state["total_requests_handled"] = previous.get("total_requests_handled", 0) + previous.get("requests_this_session", 0)
        state["first_started"] = previous.get("first_started", state["iso_timestamp"])
    else:
        state["restart_count"] = 0
        state["total_requests_handled"] = 0
        state["first_started"] = state["iso_timestamp"]
    
    state["requests_this_session"] = 0
    
    Path(STATE_FILE).write_text(json.dumps(state, indent=2, ensure_ascii=False))
    print(f"State saved to {STATE_FILE}")
    print(f"  workers: {state['worker_count']}")
    print(f"  restart_count: {state['restart_count']}")
    print(f"  first_started: {state['first_started']}")
    return state


def load_state():
    """Load state from file."""
    if not os.path.exists(STATE_FILE):
        return None
    try:
        return json.loads(Path(STATE_FILE).read_text())
    except Exception:
        return None


def restore_state():
    """Restore cluster from saved state — restart dead workers."""
    state = load_state()
    if not state:
        print("No saved state found")
        return False
    
    print(f"Restoring from state saved at {state['iso_timestamp']}")
    print(f"  expected workers: {state['worker_count']}")
    
    current = get_current_state()
    alive_workers = [w for w in current["workers"] if w["alive"]]
    dead_workers = state["workers"]  # from saved state
    
    print(f"  currently alive: {len(alive_workers)}")
    
    # If master is dead, start it
    if not current["master"]["alive"]:
        print("  master dead — starting...")
        import subprocess
        subprocess.run(["python3", "/home/z/my-project/scripts/v937_daemon.py", "--start"], timeout=30)
        time.sleep(3)
    
    # If fewer workers alive than expected, restart cluster
    if len(alive_workers) < state["worker_count"]:
        print(f"  starting cluster with {state['worker_count']} workers...")
        import subprocess
        subprocess.run(
            ["python3", CLUSTER, "--start", "--workers", str(state["worker_count"])],
            capture_output=True, text=True, timeout=60
        )
        # Increment restart count
        state["restart_count"] = state.get("restart_count", 0) + 1
        Path(STATE_FILE).write_text(json.dumps(state, indent=2, ensure_ascii=False))
        print(f"  cluster restarted (restart_count={state['restart_count']})")
    else:
        print("  all workers alive — no action needed")
    
    # Log to audit trail
    try:
        import subprocess
        subprocess.run([
            "python3", "/home/z/my-project/scripts/v934_infra.py", "audit-add",
            "--claim", f"cluster state restored: {state['worker_count']} workers, restart_count={state['restart_count']}",
            "--task-id", "v941-cluster-restore"
        ], capture_output=True, timeout=10)
    except Exception:
        pass
    
    return True


def migrate_state():
    """Update state file with current PIDs (after manual restart)."""
    current = get_current_state()
    previous = load_state()
    
    if previous:
        current["restart_count"] = previous.get("restart_count", 0)
        current["total_requests_handled"] = previous.get("total_requests_handled", 0)
        current["first_started"] = previous.get("first_started", current["iso_timestamp"])
    else:
        current["restart_count"] = 0
        current["total_requests_handled"] = 0
        current["first_started"] = current["iso_timestamp"]
    
    current["requests_this_session"] = 0
    
    Path(STATE_FILE).write_text(json.dumps(current, indent=2, ensure_ascii=False))
    print("State migrated to current PIDs")
    return current


def show_status():
    """Show state file + current state."""
    state = load_state()
    if state:
        print("=== Saved State ===")
        print(json.dumps(state, indent=2))
    else:
        print("No saved state")
    
    print("\n=== Current State ===")
    current = get_current_state()
    print(json.dumps(current, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["save", "restore", "status", "migrate"])
    args = parser.parse_args()
    
    if args.command == "save":
        save_state()
    elif args.command == "restore":
        restore_state()
    elif args.command == "status":
        show_status()
    elif args.command == "migrate":
        migrate_state()


if __name__ == "__main__":
    main()
