#!/usr/bin/env python3
"""
v940_websocket.py — WEBSOCKET SERVER v9.40
============================================
Bidirectional WebSocket server (vs SSE one-way in v9.39).

Features:
- Real-time bidirectional chat (client can send messages, server pushes updates)
- Live gate execution updates (server pushes as gates complete)
- Cluster status streaming
- Cancel ongoing requests (client sends cancel message)

Usage:
    python3 v940_websocket.py --port 8765
    
    # Client (browser JS):
    ws = new WebSocket('ws://localhost:8765/ws');
    ws.onmessage = (e) => console.log(JSON.parse(e.data));
    ws.send(JSON.stringify({type: 'chat', prompt: 'Hello'}));
    ws.send(JSON.stringify({type: 'cancel'}));
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# WebSocket requires websockets package
try:
    import websockets
    import websockets.server
except ImportError:
    print("Installing websockets...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets
    import websockets.server

sys.path.insert(0, "/home/z/my-project/scripts")

DAEMON = "/home/z/my-project/scripts/v937_daemon.py"
LLM_CLIENT = "/home/z/my-project/scripts/v938_llm_client.py"
CLUSTER = "/home/z/my-project/scripts/v939_cluster.py"


async def daemon_cmd_async(cmd, args=None, timeout=120):
    """Run daemon command in executor (non-blocking)."""
    loop = asyncio.get_event_loop()
    def _run():
        try:
            cmd_args = ["--args"] + (args or [])
            result = subprocess.run(
                ["python3", DAEMON, "--run", cmd] + cmd_args,
                capture_output=True, text=True, timeout=timeout
            )
            return json.loads(result.stdout.strip())
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return await loop.run_in_executor(None, _run)


async def llm_chat_async(prompt, system=""):
    """Run LLM chat in executor."""
    loop = asyncio.get_event_loop()
    def _run():
        try:
            result = subprocess.run(
                ["python3", LLM_CLIENT, "chat", "--prompt", prompt, "--system", system],
                capture_output=True, text=True, timeout=180
            )
            return json.loads(result.stdout.strip())
        except Exception as e:
            return {"error": str(e)}
    return await loop.run_in_executor(None, _run)


async def handle_client(websocket, path="/ws"):
    """Handle WebSocket client connection."""
    client_id = f"client_{int(time.time()*1000) % 100000}"
    print(f"[ws] {client_id} connected")
    
    # Track active tasks for cancellation
    active_tasks = {}
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"type": "error", "error": "invalid JSON"}))
                continue
            
            msg_type = data.get("type")
            
            if msg_type == "chat":
                prompt = data.get("prompt", "")
                system = data.get("system", "")
                
                # Send acknowledgment
                await websocket.send(json.dumps({
                    "type": "chat_start",
                    "client_id": client_id,
                    "timestamp": time.time(),
                }))
                
                # Run LLM chat (cancellable)
                task = asyncio.create_task(llm_chat_stream_to_client(websocket, prompt, system, client_id))
                active_tasks[client_id] = task
                
            elif msg_type == "cancel":
                # Cancel active task
                if client_id in active_tasks:
                    active_tasks[client_id].cancel()
                    await websocket.send(json.dumps({"type": "cancelled", "client_id": client_id}))
                    
            elif msg_type == "run_gates":
                # Run all gates, push results as they complete
                await run_gates_stream(websocket, client_id)
                
            elif msg_type == "cluster_status":
                # Get cluster status
                loop = asyncio.get_event_loop()
                def _cluster_status():
                    try:
                        result = subprocess.run(
                            ["python3", CLUSTER, "--status"],
                            capture_output=True, text=True, timeout=10
                        )
                        return result.stdout
                    except Exception as e:
                        return str(e)
                status = await loop.run_in_executor(None, _cluster_status)
                await websocket.send(json.dumps({
                    "type": "cluster_status",
                    "status": status,
                    "timestamp": time.time(),
                }))
                
            elif msg_type == "ping":
                await websocket.send(json.dumps({"type": "pong", "timestamp": time.time()}))
                
            else:
                await websocket.send(json.dumps({"type": "error", "error": f"unknown type: {msg_type}"}))
    
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # Cancel any active tasks
        for task in active_tasks.values():
            task.cancel()
        print(f"[ws] {client_id} disconnected")


async def llm_chat_stream_to_client(websocket, prompt, system, client_id):
    """Stream LLM response to client word-by-word."""
    try:
        result = await llm_chat_async(prompt, system)
        
        if "error" in result:
            await websocket.send(json.dumps({
                "type": "error",
                "error": result["error"],
                "client_id": client_id,
            }))
            return
        
        content = result.get("content", "")
        model = result.get("model", "unknown")
        cached = result.get("cached", False)
        tokens = result.get("tokens", 0)
        
        # Send metadata
        await websocket.send(json.dumps({
            "type": "chat_meta",
            "model": model,
            "cached": cached,
            "tokens": tokens,
            "client_id": client_id,
        }))
        
        # Stream content word-by-word
        words = content.split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            await websocket.send(json.dumps({
                "type": "chat_chunk",
                "content": chunk,
                "client_id": client_id,
                "progress": (i + 1) / len(words) if words else 1.0,
            }))
            await asyncio.sleep(0.02)  # 20ms per word
        
        await websocket.send(json.dumps({
            "type": "chat_done",
            "client_id": client_id,
        }))
        
    except asyncio.CancelledError:
        await websocket.send(json.dumps({
            "type": "chat_cancelled",
            "client_id": client_id,
        }))
    except Exception as e:
        await websocket.send(json.dumps({
            "type": "error",
            "error": str(e),
            "client_id": client_id,
        }))


async def run_gates_stream(websocket, client_id):
    """Run all gates, push results as they complete."""
    gates = [
        {"cmd": "g0_check", "args": [], "name": "G0 Immutable Core"},
        {"cmd": "z3_verify", "args": [], "name": "G0-Z3 Formal Verify"},
        {"cmd": "bert_check_primary_goal", "args": [], "name": "G58 BERT"},
        {"cmd": "bert_check_primary_goal", "args": ["sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"], "name": "G60 Multilingual"},
        {"cmd": "bert_check_primary_goal", "args": ["sentence-transformers/paraphrase-MiniLM-L6-v2"], "name": "G61 Paraphrase"},
    ]
    
    await websocket.send(json.dumps({
        "type": "gates_start",
        "total": len(gates),
        "client_id": client_id,
    }))
    
    for i, gate in enumerate(gates):
        result = await daemon_cmd_async(gate["cmd"], gate["args"])
        
        # Determine pass/fail
        passed = False
        detail = ""
        if result.get("ok") and result.get("result"):
            r = result["result"]
            if gate["cmd"] == "g0_check":
                passed = r.get("pass", False)
                detail = r.get("actual_hash", "")
            elif gate["cmd"] == "z3_verify":
                passed = r.get("proven", False)
                detail = f"{r.get('time_sec', 0)}s"
            else:
                passed = r.get("pass", False)
                detail = f"sim={r.get('similarity', 0):.4f}"
        
        await websocket.send(json.dumps({
            "type": "gate_result",
            "gate": gate["name"],
            "passed": passed,
            "detail": detail,
            "progress": (i + 1) / len(gates),
            "client_id": client_id,
        }))
    
    await websocket.send(json.dumps({
        "type": "gates_done",
        "client_id": client_id,
    }))


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    
    print(f"v9.40 WebSocket server on ws://localhost:{args.port}/ws")
    print(f"Test with browser JS:")
    print(f'  ws = new WebSocket("ws://localhost:{args.port}/ws");')
    print(f'  ws.onmessage = e => console.log(JSON.parse(e.data));')
    print(f'  ws.send(JSON.stringify({{type: "chat", prompt: "Hello"}}));')
    
    async with websockets.serve(handle_client, "localhost", args.port):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
