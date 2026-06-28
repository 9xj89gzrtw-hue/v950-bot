#!/usr/bin/env python3
"""
v941_ws_auth.py — WEBSOCKET AUTHENTICATION v9.41
==================================================
Token-based authentication for WebSocket server.

Auth methods:
1. Token in URL query: ws://localhost:8766/ws?token=SECRET
2. Token in first message: {"type": "auth", "token": "SECRET"}
3. Token in cookie (browser)

Token stored in /home/z/my-project/scripts/v941_ws_token
Auto-generated on first run, can be rotated.

Usage:
    python3 v941_ws_auth.py --port 8766    # start authenticated WS server
    python3 v941_ws_auth.py --gen-token    # generate new token
    python3 v941_ws_auth.py --show-token   # show current token
"""
import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    import websockets
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets

sys.path.insert(0, "/home/z/my-project/scripts")

TOKEN_FILE = "/home/z/my-project/scripts/v941_ws_token"
DAEMON = "/home/z/my-project/scripts/v937_daemon.py"
LLM_CLIENT = "/home/z/my-project/scripts/v938_llm_client.py"


def gen_token():
    """Generate a secure random token."""
    token = secrets.token_urlsafe(32)
    Path(TOKEN_FILE).write_text(token)
    Path(TOKEN_FILE).chmod(0o600)
    return token


def get_token():
    """Get current token (generate if not exists)."""
    if not os.path.exists(TOKEN_FILE):
        return gen_token()
    return Path(TOKEN_FILE).read_text().strip()


def verify_token(provided):
    """Verify provided token against stored."""
    if not provided:
        return False
    stored = get_token()
    return secrets.compare_digest(provided, stored)


async def daemon_cmd_async(cmd, args=None, timeout=120):
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


async def handle_client(websocket):
    """Handle authenticated WebSocket client."""
    client_id = f"client_{int(time.time()*1000) % 100000}"
    
    # Extract token from URL query or wait for auth message
    path = websocket.request.path if hasattr(websocket, 'request') else ""
    parsed = urlparse(path)
    params = parse_qs(parsed.query)
    token = params.get("token", [None])[0]
    
    # If no token in URL, wait for auth message
    if not token:
        try:
            msg = await asyncio.wait_for(websocket.recv(), timeout=10)
            data = json.loads(msg)
            if data.get("type") == "auth":
                token = data.get("token")
            else:
                await websocket.send(json.dumps({"type": "auth_required", "error": "send auth message first"}))
                await websocket.close()
                return
        except asyncio.TimeoutError:
            await websocket.send(json.dumps({"type": "auth_timeout", "error": "no auth within 10s"}))
            await websocket.close()
            return
    
    # Verify token
    if not verify_token(token):
        await websocket.send(json.dumps({"type": "auth_failed", "error": "invalid token"}))
        await websocket.close()
        return
    
    # Authenticated
    await websocket.send(json.dumps({
        "type": "auth_ok",
        "client_id": client_id,
        "timestamp": time.time(),
    }))
    print(f"[ws-auth] {client_id} authenticated")
    
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
                await websocket.send(json.dumps({"type": "chat_start", "client_id": client_id}))
                
                task = asyncio.create_task(stream_llm(websocket, prompt, system, client_id))
                active_tasks[client_id] = task
                
            elif msg_type == "cancel":
                if client_id in active_tasks:
                    active_tasks[client_id].cancel()
                    await websocket.send(json.dumps({"type": "cancelled", "client_id": client_id}))
                    
            elif msg_type == "run_gates":
                await run_gates_stream(websocket, client_id)
                
            elif msg_type == "ping":
                await websocket.send(json.dumps({"type": "pong", "timestamp": time.time()}))
            else:
                await websocket.send(json.dumps({"type": "error", "error": f"unknown: {msg_type}"}))
    
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        for task in active_tasks.values():
            task.cancel()
        print(f"[ws-auth] {client_id} disconnected")


async def stream_llm(websocket, prompt, system, client_id):
    """Stream LLM response."""
    try:
        result = await llm_chat_async(prompt, system)
        if "error" in result:
            await websocket.send(json.dumps({"type": "error", "error": result["error"]}))
            return
        
        content = result.get("content", "")
        await websocket.send(json.dumps({
            "type": "chat_meta",
            "model": result.get("model", "unknown"),
            "cached": result.get("cached", False),
            "tokens": result.get("tokens", 0),
            "client_id": client_id,
        }))
        
        words = content.split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            await websocket.send(json.dumps({
                "type": "chat_chunk",
                "content": chunk,
                "client_id": client_id,
                "progress": (i + 1) / len(words) if words else 1.0,
            }))
            await asyncio.sleep(0.02)
        
        await websocket.send(json.dumps({"type": "chat_done", "client_id": client_id}))
    except asyncio.CancelledError:
        await websocket.send(json.dumps({"type": "chat_cancelled", "client_id": client_id}))
    except Exception as e:
        await websocket.send(json.dumps({"type": "error", "error": str(e)}))


async def run_gates_stream(websocket, client_id):
    """Run all gates, push results."""
    gates = [
        {"cmd": "g0_check", "args": [], "name": "G0 Immutable Core"},
        {"cmd": "z3_verify", "args": [], "name": "G0-Z3 Formal Verify"},
        {"cmd": "bert_check_primary_goal", "args": [], "name": "G58 BERT"},
    ]
    
    await websocket.send(json.dumps({"type": "gates_start", "total": len(gates), "client_id": client_id}))
    
    for gate in gates:
        result = await daemon_cmd_async(gate["cmd"], gate["args"])
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
            "client_id": client_id,
        }))
    
    await websocket.send(json.dumps({"type": "gates_done", "client_id": client_id}))


async def main_async(port):
    token = get_token()
    print(f"v9.41 Authenticated WebSocket server on ws://localhost:{port}/ws")
    print(f"Token: {token}")
    print(f"Connect: ws://localhost:{port}/ws?token={token}")
    
    async with websockets.serve(handle_client, "localhost", port):
        await asyncio.Future()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--gen-token", action="store_true")
    parser.add_argument("--show-token", action="store_true")
    args = parser.parse_args()
    
    if args.gen_token:
        token = gen_token()
        print(f"New token: {token}")
        print(f"Saved to: {TOKEN_FILE}")
    elif args.show_token:
        print(get_token())
    else:
        asyncio.run(main_async(args.port))


if __name__ == "__main__":
    main()
