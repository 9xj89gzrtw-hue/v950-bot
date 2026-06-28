#!/usr/bin/env python3
"""
v946_edge.py — EDGE COMPUTING SIMULATION v9.46
================================================
Simulate edge computing: run inference closer to user.

Real edge computing: Cloudflare Workers, AWS Lambda@Edge, CDN nodes.
This simulation: detect user "region" (simulated), route to nearest edge node.

Edge nodes cache popular responses, reducing latency for repeat queries.

Architecture:
- 5 simulated edge nodes (US-East, US-West, EU, Asia, China)
- Each node has local cache (LRU, 100 entries)
- Request routed to nearest node based on "user region"
- If cache miss → forward to origin (daemon)
- If cache hit → instant response (0ms latency)

Usage:
    python3 v946_edge.py request --prompt "What is 2+2?" --region eu
    python3 v946_edge.py status
    python3 v946_edge.py warm --node eu --prompt "common question"
"""
import argparse
import hashlib
import json
import os
import sys
import time
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, "/home/z/my-project/scripts")

STATE_FILE = "/home/z/my-project/scripts/v946_edge_state.json"

# Simulated edge nodes with latency to "origin" (daemon)
EDGE_NODES = {
    "us-east": {"name": "US-East (Virginia)", "latency_to_origin_ms": 50, "latency_to_user_ms": 10},
    "us-west": {"name": "US-West (Oregon)", "latency_to_origin_ms": 80, "latency_to_user_ms": 15},
    "eu": {"name": "EU (Frankfurt)", "latency_to_origin_ms": 30, "latency_to_user_ms": 8},
    "asia": {"name": "Asia (Singapore)", "latency_to_origin_ms": 120, "latency_to_user_ms": 20},
    "china": {"name": "China (Beijing)", "latency_to_origin_ms": 15, "latency_to_user_ms": 5},
}

CACHE_SIZE = 100  # per node


class EdgeNode:
    """Simulated edge node with LRU cache."""
    
    def __init__(self, node_id, config):
        self.id = node_id
        self.name = config["name"]
        self.latency_to_origin = config["latency_to_origin_ms"]
        self.latency_to_user = config["latency_to_user_ms"]
        self.cache = OrderedDict()  # LRU cache
        self.cache_hits = 0
        self.cache_misses = 0
        self.requests_handled = 0
    
    def get_cache_key(self, prompt, system=""):
        return hashlib.sha256(f"{prompt}|{system}".encode()).hexdigest()[:16]
    
    def lookup(self, prompt, system=""):
        """Check local cache. Returns (cached_response, is_hit)."""
        key = self.get_cache_key(prompt, system)
        if key in self.cache:
            # LRU: move to end
            self.cache.move_to_end(key)
            self.cache_hits += 1
            return self.cache[key], True
        self.cache_misses += 1
        return None, False
    
    def store(self, prompt, system, response):
        """Store response in cache."""
        key = self.get_cache_key(prompt, system)
        self.cache[key] = response
        # LRU eviction
        if len(self.cache) > CACHE_SIZE:
            self.cache.popitem(last=False)
    
    def handle_request(self, prompt, system="", origin_func=None):
        """Handle request: check cache, forward to origin if miss."""
        self.requests_handled += 1
        start = time.time()
        
        # Check cache
        cached, hit = self.lookup(prompt, system)
        if hit:
            return {
                "response": cached,
                "cache_hit": True,
                "node": self.id,
                "latency_ms": self.latency_to_user,  # edge → user only
                "origin_called": False,
            }
        
        # Cache miss → forward to origin
        if origin_func:
            origin_response = origin_func(prompt, system)
        else:
            origin_response = "[simulated origin response]"
        
        # Store in cache
        self.store(prompt, system, origin_response)
        
        return {
            "response": origin_response,
            "cache_hit": False,
            "node": self.id,
            "latency_ms": self.latency_to_user + self.latency_to_origin,  # user → edge → origin → edge → user
            "origin_called": True,
        }
    
    def stats(self):
        total = self.cache_hits + self.cache_misses
        hit_rate = self.cache_hits / total if total > 0 else 0
        return {
            "id": self.id,
            "name": self.name,
            "cache_size": len(self.cache),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": round(hit_rate, 3),
            "requests": self.requests_handled,
        }


# ============================================================================
# EDGE NETWORK
# ============================================================================

class EdgeNetwork:
    """Manage multiple edge nodes."""
    
    def __init__(self):
        self.nodes = {nid: EdgeNode(nid, cfg) for nid, cfg in EDGE_NODES.items()}
    
    def route_request(self, prompt, system="", user_region="eu", origin_func=None):
        """Route request to nearest edge node."""
        # Find nearest node (simulated: user region matches node)
        node_id = user_region if user_region in self.nodes else "eu"
        node = self.nodes[node_id]
        
        result = node.handle_request(prompt, system, origin_func)
        result["user_region"] = user_region
        result["node_name"] = node.name
        return result
    
    def warm_node(self, node_id, prompt, system="", response=None):
        """Pre-warm a node's cache."""
        if node_id not in self.nodes:
            return {"error": f"unknown node: {node_id}"}
        node = self.nodes[node_id]
        node.store(prompt, system, response or "[pre-warmed]")
        return {"warmed": True, "node": node_id, "cache_size": len(node.cache)}
    
    def status(self):
        return {
            "nodes": {nid: n.stats() for nid, n in self.nodes.items()},
            "total_requests": sum(n.requests_handled for n in self.nodes.values()),
            "total_cache_hits": sum(n.cache_hits for n in self.nodes.values()),
            "total_cache_entries": sum(len(n.cache) for n in self.nodes.values()),
        }


_NETWORK = None


def get_network():
    global _NETWORK
    if _NETWORK is None:
        _NETWORK = EdgeNetwork()
    return _NETWORK


def origin_llm_call(prompt, system=""):
    """Simulated origin: call daemon LLM."""
    import subprocess
    try:
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v937_daemon.py", "--run", "llm_chat", "--args", prompt, system],
            capture_output=True, text=True, timeout=180
        )
        data = json.loads(result.stdout.strip())
        if data.get("ok"):
            return data["result"].get("content", "")
    except Exception:
        pass
    return "[origin unavailable]"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["request", "status", "warm", "benchmark"])
    parser.add_argument("--prompt", help="prompt")
    parser.add_argument("--system", default="")
    parser.add_argument("--region", default="eu", choices=list(EDGE_NODES.keys()))
    parser.add_argument("--node", help="node to warm")
    parser.add_argument("--no-origin", action="store_true", help="don't call real LLM")
    args = parser.parse_args()
    
    net = get_network()
    
    if args.command == "request":
        if not args.prompt:
            print("--prompt required")
            sys.exit(2)
        origin_func = None if args.no_origin else origin_llm_call
        result = net.route_request(args.prompt, args.system, args.region, origin_func)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif args.command == "status":
        print(json.dumps(net.status(), indent=2))
    
    elif args.command == "warm":
        if not args.node or not args.prompt:
            print("--node and --prompt required")
            sys.exit(2)
        result = net.warm_node(args.node, args.prompt, args.system)
        print(json.dumps(result, indent=2))
    
    elif args.command == "benchmark":
        # Simulate 10 requests across regions
        print("=== Edge Computing Benchmark ===\n")
        prompts = ["What is 2+2?", "Hello", "What is Python?", "What is 2+2?", "Hello"]
        
        for region in ["eu", "us-east", "china"]:
            print(f"Region: {region}")
            for prompt in prompts:
                result = net.route_request(prompt, "", region, origin_func=None)
                hit = "HIT" if result["cache_hit"] else "MISS"
                print(f"  [{hit}] {prompt[:30]:<30} latency={result['latency_ms']}ms")
            print()


if __name__ == "__main__":
    main()
