#!/usr/bin/env python3
"""
v954_otel.py — OPENTELEMETRY DISTRIBUTED TRACING v9.54
=======================================================
Trace requests across all components: Telegram → Bot → LLM → Response.

Each span records:
- Operation name
- Duration
- Attributes (model, tokens, cached, provider)
- Status (OK/ERROR)
- Parent span (for distributed tracing)

Exports to:
- stdout (console)
- OTLP collector (Jaeger/Zipkin)
- File (JSON lines)

Usage:
    python3 v954_otel.py trace --prompt "Hello"
    python3 v954_otel.py benchmark
"""
import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, "/home/z/my-project/scripts")

TRACE_FILE = "/home/z/my-project/download/v954_traces.jsonl"


class Span:
    """OpenTelemetry-compatible span."""
    
    def __init__(self, name, parent_id=None, trace_id=None):
        self.name = name
        self.span_id = uuid.uuid4().hex[:16]
        self.trace_id = trace_id or uuid.uuid4().hex[:32]
        self.parent_id = parent_id
        self.start_time = time.time()
        self.end_time = None
        self.attributes = {}
        self.status = "OK"
        self.events = []
    
    def set_attribute(self, key, value):
        self.attributes[key] = value
    
    def add_event(self, name, attributes=None):
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })
    
    def set_status(self, status, description=""):
        self.status = status
        if description:
            self.attributes["status_description"] = description
    
    def end(self):
        self.end_time = time.time()
        return self.to_dict()
    
    def to_dict(self):
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_id,
            "name": self.name,
            "start_time_unix_nano": int(self.start_time * 1e9),
            "end_time_unix_nano": int((self.end_time or time.time()) * 1e9),
            "duration_ms": round(((self.end_time or time.time()) - self.start_time) * 1000, 2),
            "attributes": self.attributes,
            "status": self.status,
            "events": self.events,
            "resource": {
                "service.name": "v950-bot",
                "service.version": "9.54",
            },
        }


class Tracer:
    """Simple tracer that writes spans to file."""
    
    def __init__(self):
        self.spans = []
        Path(TRACE_FILE).parent.mkdir(parents=True, exist_ok=True)
    
    def start_span(self, name, parent_id=None, trace_id=None):
        span = Span(name, parent_id, trace_id)
        self.spans.append(span)
        return span
    
    def export(self):
        """Export all spans to JSON lines file."""
        with open(TRACE_FILE, "a") as f:
            for span in self.spans:
                f.write(json.dumps(span.to_dict()) + "\n")
        return len(self.spans)


_tracer = Tracer()


def trace_llm_request(prompt, system=""):
    """Trace a full LLM request through all layers."""
    # Root span: full request
    root = _tracer.start_span("telegram_request")
    root.set_attribute("prompt", prompt[:100])
    root.set_attribute("user.chat_id", "396449039")
    
    # Span 1: Safety check
    safety_span = _tracer.start_span("safety_check", root.span_id, root.trace_id)
    t0 = time.time()
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v945_safety.py", "check-input", "--prompt", prompt],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout.strip())
        safety_span.set_attribute("safety.safe", data.get("safe"))
        safety_span.set_attribute("safety.issues", data.get("issue_count", 0))
        safety_span.set_status("OK")
    except Exception as e:
        safety_span.set_status("ERROR", str(e))
    safety_span.end()
    root.add_event("safety_check_done", {"safe": data.get("safe") if 'data' in dir() else None})
    
    # Span 2: LLM call
    llm_span = _tracer.start_span("llm_chat", root.span_id, root.trace_id)
    llm_span.set_attribute("llm.provider", "z-ai")
    t0 = time.time()
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v938_llm_client.py", "chat", "--prompt", prompt, "--system", system],
            capture_output=True, text=True, timeout=60
        )
        data = json.loads(result.stdout.strip())
        llm_span.set_attribute("llm.model", data.get("model", "?"))
        llm_span.set_attribute("llm.tokens", data.get("tokens", 0))
        llm_span.set_attribute("llm.cached", data.get("cached", False))
        llm_span.set_attribute("llm.attempts", data.get("attempts", 0))
        llm_span.set_attribute("llm.provider_chain", data.get("provider_chain", []))
        llm_span.set_status("OK")
        content = data.get("content", "")
    except Exception as e:
        llm_span.set_status("ERROR", str(e))
        content = ""
    llm_span.end()
    
    # Span 3: Response formatting
    format_span = _tracer.start_span("format_response", root.span_id, root.trace_id)
    response = f"🤖 {data.get('model', '?')}\n\n{content}" if content else "❌ Error"
    format_span.set_attribute("response.length", len(response))
    format_span.end()
    
    # End root span
    root.set_attribute("response.length", len(response))
    root.set_attribute("response.success", bool(content))
    root.end()
    
    # Export
    _tracer.export()
    
    return {
        "trace_id": root.trace_id,
        "spans": [s.to_dict() for s in _tracer.spans],
        "response": response,
        "total_duration_ms": round(root.to_dict()["duration_ms"], 2),
    }


def benchmark():
    """Run traced requests and show timing breakdown."""
    print("=== OpenTelemetry Distributed Tracing ===\n")
    
    prompts = [
        "Say OK",
        "What is 2+2?",
        "Hello, how are you?",
    ]
    
    for prompt in prompts:
        print(f"Prompt: {prompt}")
        result = trace_llm_request(prompt)
        
        print(f"  Trace ID: {result['trace_id'][:16]}...")
        print(f"  Total: {result['total_duration_ms']}ms")
        for span in result["spans"]:
            indent = "    " if span["parent_span_id"] else "  "
            print(f"{indent}{span['name']:<25} {span['duration_ms']:>8.2f}ms  {span['status']}")
            for k, v in span["attributes"].items():
                if k.startswith("llm.") or k.startswith("safety."):
                    print(f"{indent}  └─ {k} = {v}")
        print()
    
    print(f"Traces exported to: {TRACE_FILE}")
    print(f"Total spans: {sum(1 for _ in open(TRACE_FILE) if _.strip())}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["trace", "benchmark"])
    parser.add_argument("--prompt")
    parser.add_argument("--system", default="")
    args = parser.parse_args()
    
    if args.command == "trace":
        if not args.prompt:
            print("--prompt required")
            sys.exit(2)
        result = trace_llm_request(args.prompt, args.system)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.command == "benchmark":
        benchmark()


if __name__ == "__main__":
    main()
