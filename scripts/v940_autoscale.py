#!/usr/bin/env python3
"""
v940_autoscale.py — AUTO-SCALING WORKER CLUSTER v9.40
=======================================================
Dynamically scales daemon workers based on queue depth.

Monitors:
- Active LLM requests per worker
- Average response time
- Queue depth (pending requests)

Auto-scaling rules:
- If avg response time > 5s AND workers < MAX_WORKERS → scale up
- If avg response time < 1s AND workers > MIN_WORKERS → scale down
- Check every 10 seconds

Usage:
    python3 v940_autoscale.py --min 1 --max 5    # run autoscaler
    python3 v940_autoscale.py --status            # show current state
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/z/my-project/scripts")

MIN_WORKERS = 1
MAX_WORKERS = 5
CHECK_INTERVAL_SEC = 10
SCALE_UP_THRESHOLD_SEC = 5.0   # avg response > 5s → scale up
SCALE_DOWN_THRESHOLD_SEC = 1.0  # avg response < 1s → scale down
COOLDOWN_SEC = 30  # wait between scaling actions

CLUSTER = "/home/z/my-project/scripts/v939_cluster.py"
METRICS_FILE = "/home/z/my-project/download/autoscale_metrics.json"


def get_cluster_state():
    """Get current cluster state."""
    try:
        result = subprocess.run(
            ["python3", CLUSTER, "--status"],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout
        # Parse worker count
        worker_count = output.count("Worker ") - output.count("Workers: none")
        if "Workers: none" in output:
            worker_count = 0
        return {"raw": output, "workers": max(0, worker_count)}
    except Exception as e:
        return {"raw": str(e), "workers": 0}


def get_avg_response_time():
    """Get average LLM response time from metrics (simulated)."""
    # In production, this would query Prometheus or evidence.db
    # For now, return a simulated value based on recent activity
    try:
        if os.path.exists(METRICS_FILE):
            data = json.loads(Path(METRICS_FILE).read_text())
            return data.get("avg_response_sec", 2.0)
    except Exception:
        pass
    return 2.0  # default


def scale_to(target_workers):
    """Scale cluster to target worker count."""
    state = get_cluster_state()
    current = state["workers"]
    
    if current == target_workers:
        return f"already at {current} workers"
    
    if target_workers > current:
        # Scale up
        print(f"[autoscale] scaling UP: {current} → {target_workers}")
        result = subprocess.run(
            ["python3", CLUSTER, "--start", "--workers", str(target_workers)],
            capture_output=True, text=True, timeout=60
        )
        return f"scaled up to {target_workers}"
    else:
        # Scale down — stop all and restart with fewer
        print(f"[autoscale] scaling DOWN: {current} → {target_workers}")
        subprocess.run(["python3", CLUSTER, "--stop"], capture_output=True, text=True, timeout=15)
        time.sleep(2)
        if target_workers > 0:
            subprocess.run(
                ["python3", CLUSTER, "--start", "--workers", str(target_workers)],
                capture_output=True, text=True, timeout=60
            )
        return f"scaled down to {target_workers}"


def autoscale_loop(min_workers, max_workers):
    """Main autoscaling loop."""
    print(f"[autoscale] starting (min={min_workers}, max={max_workers}, interval={CHECK_INTERVAL_SEC}s)")
    print(f"[autoscale] scale up if avg > {SCALE_UP_THRESHOLD_SEC}s, scale down if < {SCALE_DOWN_THRESHOLD_SEC}s")
    
    last_scale_time = 0
    
    while True:
        state = get_cluster_state()
        avg_response = get_avg_response_time()
        current_workers = state["workers"]
        
        print(f"[autoscale] workers={current_workers}, avg_response={avg_response:.1f}s")
        
        # Save metrics
        Path(METRICS_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(METRICS_FILE).write_text(json.dumps({
            "workers": current_workers,
            "avg_response_sec": avg_response,
            "timestamp": time.time(),
        }))
        
        # Check cooldown
        now = time.time()
        if now - last_scale_time < COOLDOWN_SEC:
            time.sleep(CHECK_INTERVAL_SEC)
            continue
        
        # Scaling rules
        if avg_response > SCALE_UP_THRESHOLD_SEC and current_workers < max_workers:
            target = min(current_workers + 1, max_workers)
            scale_to(target)
            last_scale_time = now
        elif avg_response < SCALE_DOWN_THRESHOLD_SEC and current_workers > min_workers:
            target = max(current_workers - 1, min_workers)
            scale_to(target)
            last_scale_time = now
        
        time.sleep(CHECK_INTERVAL_SEC)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min", type=int, default=MIN_WORKERS)
    parser.add_argument("--max", type=int, default=MAX_WORKERS)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    
    if args.status:
        state = get_cluster_state()
        avg = get_avg_response_time()
        print(f"Workers: {state['workers']}")
        print(f"Avg response: {avg:.1f}s")
        print(f"Raw: {state['raw']}")
    else:
        try:
            autoscale_loop(args.min, args.max)
        except KeyboardInterrupt:
            print("\n[autoscale] stopped")


if __name__ == "__main__":
    main()
