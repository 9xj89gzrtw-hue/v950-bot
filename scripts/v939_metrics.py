#!/usr/bin/env python3
"""
v939_metrics.py — PROMETHEUS METRICS v9.39
============================================
Collects and exposes metrics in Prometheus format.

Metrics tracked:
- v939_gate_executions_total{gate, status} — counter
- v939_gate_duration_seconds{gate} — histogram
- v939_llm_calls_total{provider, status} — counter
- v939_llm_duration_seconds{provider} — histogram
- v939_cache_hits_total — counter
- v939_cache_misses_total — counter
- v939_daemon_uptime_seconds — gauge
- v939_daemon_resources_loaded — gauge
- v939_cluster_workers_active — gauge

Usage:
    # As module:
    from v939_metrics import Metrics
    Metrics.inc_gate("g0_check", "pass")
    Metrics.observe_gate_duration("g0_check", 0.065)
    
    # As standalone HTTP exporter:
    python3 v939_metrics.py --port 9090  # serves /metrics
"""
import argparse
import http.server
import json
import os
import socketserver
import sqlite3
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

DB_PATH = "/home/z/my-project/evidence.db"
METRICS_TABLE = "prometheus_metrics"

_START_TIME = time.time()

# In-memory metrics (fast, no DB overhead for hot path)
_counters = defaultdict(lambda: defaultdict(float))
_histograms = defaultdict(lambda: defaultdict(list))
_gauges = defaultdict(float)


class Metrics:
    """Thread-safe metrics collector."""
    
    _lock = threading.Lock()
    
    @classmethod
    def inc_gate(cls, gate, status):
        """Increment gate execution counter. status: pass/fail."""
        with cls._lock:
            _counters["gate_executions"][(gate, status)] += 1
    
    @classmethod
    def observe_gate_duration(cls, gate, seconds):
        """Record gate execution duration."""
        with cls._lock:
            _histograms["gate_duration"][gate].append(seconds)
            # Keep only last 100 samples
            if len(_histograms["gate_duration"][gate]) > 100:
                _histograms["gate_duration"][gate] = _histograms["gate_duration"][gate][-100:]
    
    @classmethod
    def inc_llm_call(cls, provider, status):
        """Increment LLM call counter. status: success/fail/cache_hit."""
        with cls._lock:
            _counters["llm_calls"][(provider, status)] += 1
    
    @classmethod
    def observe_llm_duration(cls, provider, seconds):
        """Record LLM call duration."""
        with cls._lock:
            _histograms["llm_duration"][provider].append(seconds)
            if len(_histograms["llm_duration"][provider]) > 100:
                _histograms["llm_duration"][provider] = _histograms["llm_duration"][provider][-100:]
    
    @classmethod
    def inc_cache_hit(cls):
        with cls._lock:
            _counters["cache"]["hit"] += 1
    
    @classmethod
    def inc_cache_miss(cls):
        with cls._lock:
            _counters["cache"]["miss"] += 1
    
    @classmethod
    def set_gauge(cls, name, value, labels=None):
        with cls._lock:
            key = (name, tuple(labels.items())) if labels else (name, ())
            _gauges[key] = value
    
    @classmethod
    def get_uptime(cls):
        return time.time() - _START_TIME
    
    @classmethod
    def format_prometheus(cls):
        """Format all metrics in Prometheus exposition format."""
        lines = []
        
        # Gate executions
        lines.append("# HELP v939_gate_executions_total Total gate executions by gate and status")
        lines.append("# TYPE v939_gate_executions_total counter")
        with cls._lock:
            for (gate, status), count in _counters["gate_executions"].items():
                lines.append(f'v939_gate_executions_total{{gate="{gate}",status="{status}"}} {int(count)}')
        
        # Gate duration
        lines.append("# HELP v939_gate_duration_seconds Gate execution duration")
        lines.append("# TYPE v939_gate_duration_seconds summary")
        with cls._lock:
            for gate, durations in _histograms["gate_duration"].items():
                if durations:
                    avg = sum(durations) / len(durations)
                    lines.append(f'v939_gate_duration_seconds{{gate="{gate}",quantile="avg"}} {avg:.6f}')
                    lines.append(f'v939_gate_duration_seconds{{gate="{gate}",quantile="count"}} {len(durations)}')
        
        # LLM calls
        lines.append("# HELP v939_llm_calls_total Total LLM calls by provider and status")
        lines.append("# TYPE v939_llm_calls_total counter")
        with cls._lock:
            for (provider, status), count in _counters["llm_calls"].items():
                lines.append(f'v939_llm_calls_total{{provider="{provider}",status="{status}"}} {int(count)}')
        
        # LLM duration
        lines.append("# HELP v939_llm_duration_seconds LLM call duration")
        lines.append("# TYPE v939_llm_duration_seconds summary")
        with cls._lock:
            for provider, durations in _histograms["llm_duration"].items():
                if durations:
                    avg = sum(durations) / len(durations)
                    lines.append(f'v939_llm_duration_seconds{{provider="{provider}",quantile="avg"}} {avg:.6f}')
                    lines.append(f'v939_llm_duration_seconds{{provider="{provider}",quantile="count"}} {len(durations)}')
        
        # Cache
        lines.append("# HELP v939_cache_total Cache hits and misses")
        lines.append("# TYPE v939_cache_total counter")
        with cls._lock:
            lines.append(f'v939_cache_total{{type="hit"}} {int(_counters["cache"]["hit"])}')
            lines.append(f'v939_cache_total{{type="miss"}} {int(_counters["cache"]["miss"])}')
        
        # Gauges
        lines.append("# HELP v939_daemon_uptime_seconds Daemon uptime in seconds")
        lines.append("# TYPE v939_daemon_uptime_seconds gauge")
        lines.append(f"v939_daemon_uptime_seconds {cls.get_uptime():.1f}")
        
        lines.append("# HELP v939_daemon_resources_loaded Number of resources loaded in daemon")
        lines.append("# TYPE v939_daemon_resources_loaded gauge")
        with cls._lock:
            for (name, labels), value in _gauges.items():
                if labels:
                    label_str = ",".join(f'{k}="{v}"' for k, v in labels)
                    lines.append(f'{name}{{{label_str}}} {value}')
                else:
                    lines.append(f"{name} {value}")
        
        return "\n".join(lines) + "\n"


class MetricsHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for /metrics endpoint."""
    
    def do_GET(self):
        if self.path == "/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(Metrics.format_prometheus().encode("utf-8"))
        elif self.path == "/" or self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"v9.39 metrics exporter OK\n")
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass


def run_exporter(port=9090):
    """Run standalone Prometheus metrics exporter."""
    print(f"v9.39 Prometheus metrics exporter on http://localhost:{port}/metrics")
    with socketserver.TCPServer(("localhost", port), MetricsHandler) as httpd:
        httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9090)
    parser.add_argument("--print", action="store_true", help="print metrics and exit")
    args = parser.parse_args()
    
    if args.print:
        print(Metrics.format_prometheus())
    else:
        run_exporter(args.port)


if __name__ == "__main__":
    main()
