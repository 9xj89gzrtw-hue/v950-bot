#!/usr/bin/env python3
"""
v936_cost_dashboard.py — G54 COST-LATENCY-DASHBOARD v9.36
==========================================================
Generates HTML dashboard visualizing cost/latency metrics from evidence.db.

Reads cost_latency table (populated by v930_cost_latency.py / v934_infra.py cost-log)
and generates:
- Total tokens used per task (bar chart)
- Wall-clock time per task (bar chart)
- LLM calls vs bash calls breakdown (pie chart)
- Cumulative cost over time (line chart)
- Per-task detail table

Output: /home/z/my-project/download/cost_dashboard.html
"""
import json
import os
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

DB_PATH = "/home/z/my-project/evidence.db"
OUT_HTML = "/home/z/my-project/download/cost_dashboard.html"


def load_metrics():
    """Load all cost/latency metrics from evidence.db."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Check if table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cost_latency'")
    if not c.fetchone():
        conn.close()
        return []
    c.execute("SELECT task_id, event_type, timestamp, tokens, duration_sec, metadata FROM cost_latency ORDER BY id")
    rows = c.fetchall()
    conn.close()
    return [{"task_id": r[0], "event_type": r[1], "timestamp": r[2], "tokens": r[3], "duration_sec": r[4], "metadata": r[5]} for r in rows]


def aggregate_per_task(events):
    """Aggregate events into per-task metrics."""
    tasks = {}
    for e in events:
        tid = e["task_id"]
        if tid not in tasks:
            tasks[tid] = {
                "task_id": tid,
                "start_ts": None,
                "end_ts": None,
                "llm_calls": 0,
                "llm_tokens": 0,
                "bash_calls": 0,
                "bash_wall_sec": 0.0,
                "events": [],
            }
        t = tasks[tid]
        t["events"].append(e)
        if e["event_type"] == "start":
            t["start_ts"] = e["timestamp"]
        elif e["event_type"] == "end":
            t["end_ts"] = e["timestamp"]
        elif e["event_type"] == "llm_call":
            t["llm_calls"] += 1
            t["llm_tokens"] += e["tokens"]
        elif e["event_type"] == "bash_call":
            t["bash_calls"] += 1
            t["bash_wall_sec"] += e["duration_sec"]
    # Compute wall_clock
    for t in tasks.values():
        if t["start_ts"] and t["end_ts"]:
            try:
                t1 = datetime.fromisoformat(t["start_ts"].replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(t["end_ts"].replace("Z", "+00:00"))
                t["wall_clock_sec"] = (t2 - t1).total_seconds()
            except Exception:
                t["wall_clock_sec"] = 0
        else:
            t["wall_clock_sec"] = 0
        # Cost (all free for z-ai SDK, $0)
        t["cost_usd"] = 0.0
    return list(tasks.values())


def generate_html(tasks):
    """Generate HTML dashboard with embedded Chart.js."""
    total_tokens = sum(t["llm_tokens"] for t in tasks)
    total_llm_calls = sum(t["llm_calls"] for t in tasks)
    total_bash_calls = sum(t["bash_calls"] for t in tasks)
    total_bash_wall = sum(t["bash_wall_sec"] for t in tasks)
    
    # Prepare chart data
    task_ids = [t["task_id"][:30] for t in tasks]
    tokens_data = [t["llm_tokens"] for t in tasks]
    wall_data = [t["wall_clock_sec"] for t in tasks]
    llm_calls_data = [t["llm_calls"] for t in tasks]
    bash_calls_data = [t["bash_calls"] for t in tasks]
    
    # Table rows
    table_rows = ""
    for t in tasks:
        table_rows += f"""
        <tr>
            <td>{t['task_id']}</td>
            <td>{t['llm_calls']}</td>
            <td>{t['llm_tokens']:,}</td>
            <td>{t['bash_calls']}</td>
            <td>{t['bash_wall_sec']:.1f}s</td>
            <td>{t['wall_clock_sec']:.1f}s</td>
            <td>${t['cost_usd']:.4f}</td>
            <td>{t['start_ts'] or '-'}</td>
        </tr>"""
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>v9.36 Cost/Latency Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        body {{ font-family: -apple-system, sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #333; }}
        .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }}
        .card {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .card h3 {{ margin: 0 0 5px 0; color: #666; font-size: 12px; text-transform: uppercase; }}
        .card .value {{ font-size: 24px; font-weight: bold; color: #2563eb; }}
        .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
        .chart-container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #eee; font-size: 13px; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        tr:hover {{ background: #f8f9fa; }}
    </style>
</head>
<body>
    <h1>v9.36 Cost/Latency Dashboard</h1>
    <p>Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
    
    <div class="summary">
        <div class="card">
            <h3>Total Tasks</h3>
            <div class="value">{len(tasks)}</div>
        </div>
        <div class="card">
            <h3>Total LLM Tokens</h3>
            <div class="value">{total_tokens:,}</div>
        </div>
        <div class="card">
            <h3>Total LLM Calls</h3>
            <div class="value">{total_llm_calls}</div>
        </div>
        <div class="card">
            <h3>Total Cost</h3>
            <div class="value">${0.0:.4f}</div>
        </div>
    </div>
    
    <div class="charts">
        <div class="chart-container">
            <h3>LLM Tokens per Task</h3>
            <canvas id="tokensChart"></canvas>
        </div>
        <div class="chart-container">
            <h3>Wall-Clock Time per Task (seconds)</h3>
            <canvas id="wallChart"></canvas>
        </div>
        <div class="chart-container">
            <h3>LLM Calls vs Bash Calls</h3>
            <canvas id="callsChart"></canvas>
        </div>
        <div class="chart-container">
            <h3>Bash Wall Time per Task</h3>
            <canvas id="bashWallChart"></canvas>
        </div>
    </div>
    
    <h2>Per-Task Detail</h2>
    <table>
        <thead>
            <tr>
                <th>Task ID</th>
                <th>LLM Calls</th>
                <th>LLM Tokens</th>
                <th>Bash Calls</th>
                <th>Bash Wall</th>
                <th>Wall Clock</th>
                <th>Cost USD</th>
                <th>Start Timestamp</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>
    
    <script>
        const taskIds = {json.dumps(task_ids)};
        const tokensData = {json.dumps(tokens_data)};
        const wallData = {json.dumps(wall_data)};
        const llmCallsData = {json.dumps(llm_calls_data)};
        const bashCallsData = {json.dumps(bash_calls_data)};
        
        // Tokens chart
        new Chart(document.getElementById('tokensChart'), {{
            type: 'bar',
            data: {{
                labels: taskIds,
                datasets: [{{ label: 'LLM Tokens', data: tokensData, backgroundColor: '#2563eb' }}]
            }},
            options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
        }});
        
        // Wall clock chart
        new Chart(document.getElementById('wallChart'), {{
            type: 'bar',
            data: {{
                labels: taskIds,
                datasets: [{{ label: 'Wall Clock (s)', data: wallData, backgroundColor: '#16a34a' }}]
            }},
            options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
        }});
        
        // Calls comparison (stacked bar)
        new Chart(document.getElementById('callsChart'), {{
            type: 'bar',
            data: {{
                labels: taskIds,
                datasets: [
                    {{ label: 'LLM Calls', data: llmCallsData, backgroundColor: '#dc2626' }},
                    {{ label: 'Bash Calls', data: bashCallsData, backgroundColor: '#0891b2' }}
                ]
            }},
            options: {{ responsive: true, scales: {{ x: {{ stacked: true }}, y: {{ stacked: true }} }} }}
        }});
        
        // Bash wall time
        new Chart(document.getElementById('bashWallChart'), {{
            type: 'bar',
            data: {{
                labels: taskIds,
                datasets: [{{ label: 'Bash Wall (s)', data: {json.dumps([t['bash_wall_sec'] for t in tasks])}, backgroundColor: '#7c3aed' }}]
            }},
            options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
        }});
    </script>
</body>
</html>"""
    return html


def main():
    events = load_metrics()
    if not events:
        print("No cost/latency events found in evidence.db")
        print("Run some gates first to populate metrics, then re-run dashboard.")
        # Generate empty dashboard anyway
        html = generate_html([])
        Path(OUT_HTML).parent.mkdir(parents=True, exist_ok=True)
        Path(OUT_HTML).write_text(html, encoding="utf-8")
        print(f"Empty dashboard: {OUT_HTML}")
        return
    
    tasks = aggregate_per_task(events)
    print(f"Loaded {len(events)} events, {len(tasks)} tasks")
    print(f"Total tokens: {sum(t['llm_tokens'] for t in tasks):,}")
    print(f"Total LLM calls: {sum(t['llm_calls'] for t in tasks)}")
    print(f"Total bash calls: {sum(t['bash_calls'] for t in tasks)}")
    
    html = generate_html(tasks)
    Path(OUT_HTML).parent.mkdir(parents=True, exist_ok=True)
    Path(OUT_HTML).write_text(html, encoding="utf-8")
    print(f"\nDashboard: {OUT_HTML}")
    
    # Also save JSON summary
    summary = {
        "generated": datetime.utcnow().isoformat() + "Z",
        "total_tasks": len(tasks),
        "total_llm_tokens": sum(t["llm_tokens"] for t in tasks),
        "total_llm_calls": sum(t["llm_calls"] for t in tasks),
        "total_bash_calls": sum(t["bash_calls"] for t in tasks),
        "total_bash_wall_sec": sum(t["bash_wall_sec"] for t in tasks),
        "total_cost_usd": 0.0,
        "tasks": tasks,
    }
    out_json = Path("/home/z/my-project/download/benchmarks/cost_dashboard_summary.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"JSON summary: {out_json}")


if __name__ == "__main__":
    main()
