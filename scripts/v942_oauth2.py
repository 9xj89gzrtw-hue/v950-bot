#!/usr/bin/env python3
"""
v942_oauth2.py — OAUTH2 TOKEN PROVIDER v9.42
==============================================
OAuth2-style token provider for WebSocket authentication.

Since we can't use external OAuth2 providers (Google, GitHub) without
registration, this implements a SELF-HOSTED OAuth2-like flow:
1. Client requests access token with client_id + client_secret
2. Server validates, issues signed JWT-like token (HMAC-SHA256)
3. Client uses token for WS connections
4. Token expires after 1 hour, client must refresh

Token format: base64(header).base64(payload).base64(signature)
- header: {"alg": "HS256", "typ": "JWT"}
- payload: {"sub": client_id, "iat": timestamp, "exp": timestamp+3600, "scope": "ws:chat"}
- signature: HMAC-SHA256(header.payload, secret_key)

Usage:
    # As provider server:
    python3 v942_oauth2.py --port 8768
    
    # Get token:
    curl -X POST http://localhost:8768/token -d '{"client_id":"alice","client_secret":"secret"}'
    
    # Verify token:
    python3 v942_oauth2.py --verify TOKEN
"""
import argparse
import base64
import hashlib
import hmac
import http.server
import json
import os
import secrets
import socketserver
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs

SECRET_KEY_FILE = "/home/z/my-project/scripts/v942_oauth_secret"
CLIENTS_FILE = "/home/z/my-project/scripts/v942_oauth_clients.json"
TOKEN_TTL_SEC = 3600  # 1 hour


def get_secret_key():
    """Get or generate HMAC secret key."""
    if os.path.exists(SECRET_KEY_FILE):
        return Path(SECRET_KEY_FILE).read_text().strip().encode("utf-8")
    key = secrets.token_bytes(32)
    Path(SECRET_KEY_FILE).write_text(key.hex())
    Path(SECRET_KEY_FILE).chmod(0o600)
    return key


def load_clients():
    """Load registered clients."""
    if not os.path.exists(CLIENTS_FILE):
        # Default: create alice client
        default = {
            "alice": {"client_secret": "alice_secret_2026", "scope": "ws:chat,ws:gates"},
            "bob": {"client_secret": "bob_secret_2026", "scope": "ws:chat"},
        }
        Path(CLIENTS_FILE).write_text(json.dumps(default, indent=2))
        Path(CLIENTS_FILE).chmod(0o600)
        return default
    return json.loads(Path(CLIENTS_FILE).read_text())


def b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def b64decode(data: str) -> bytes:
    padding = 4 - len(data) % 4
    if padding < 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


def create_token(client_id, scope="ws:chat"):
    """Create signed JWT-like token."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": client_id,
        "iat": now,
        "exp": now + TOKEN_TTL_SEC,
        "scope": scope,
        "jti": secrets.token_hex(8),  # unique token id
    }
    
    header_b64 = b64encode(json.dumps(header).encode())
    payload_b64 = b64encode(json.dumps(payload).encode())
    
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(get_secret_key(), signing_input, hashlib.sha256).digest()
    sig_b64 = b64encode(signature)
    
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_token(token):
    """Verify token signature and expiry. Returns payload or None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        
        # Verify signature
        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.new(get_secret_key(), signing_input, hashlib.sha256).digest()
        actual_sig = b64decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        
        # Check expiry
        payload = json.loads(b64decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        
        return payload
    except Exception:
        return None


class OAuth2Handler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for OAuth2 token endpoint."""
    
    def do_POST(self):
        if self.path == "/token":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            
            # Parse body (JSON or form-encoded)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = {k: v[0] for k, v in parse_qs(body).items()}
            
            client_id = data.get("client_id")
            client_secret = data.get("client_secret")
            grant_type = data.get("grant_type", "client_credentials")
            
            clients = load_clients()
            
            if client_id not in clients:
                self._error(401, "invalid_client", "Unknown client_id")
                return
            
            if clients[client_id]["client_secret"] != client_secret:
                self._error(401, "invalid_client", "Bad secret")
                return
            
            scope = clients[client_id].get("scope", "ws:chat")
            token = create_token(client_id, scope)
            
            response = {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": TOKEN_TTL_SEC,
                "scope": scope,
            }
            self._json(response)
        
        elif self.path == "/verify":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
                token = data.get("token")
            except json.JSONDecodeError:
                token = None
            
            if not token:
                self._error(400, "invalid_request", "token required")
                return
            
            payload = verify_token(token)
            if payload:
                self._json({"valid": True, "payload": payload})
            else:
                self._error(401, "invalid_token", "Token invalid or expired")
        
        else:
            self._error(404, "not_found", "Unknown endpoint")
    
    def do_GET(self):
        if self.path == "/.well-known/oauth-authorization-server":
            # OAuth2 server metadata
            self._json({
                "issuer": "v9.42-oauth2",
                "token_endpoint": "/token",
                "verification_endpoint": "/verify",
                "token_endpoint_auth_methods_supported": ["client_secret_post"],
                "grant_types_supported": ["client_credentials"],
                "token_ttl_sec": TOKEN_TTL_SEC,
            })
        elif self.path == "/health":
            self._json({"status": "ok"})
        else:
            self._error(404, "not_found", "Unknown endpoint")
    
    def _json(self, obj, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())
    
    def _error(self, status, error, description):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": error, "error_description": description}).encode())
    
    def log_message(self, *args):
        pass


def run_server(port=8768):
    print(f"v9.42 OAuth2 token provider on http://localhost:{port}")
    print(f"  POST /token        — get access token (client_id + client_secret)")
    print(f"  POST /verify       — verify token")
    print(f"  GET  /.well-known/oauth-authorization-server")
    print()
    print("Registered clients:")
    for cid, info in load_clients().items():
        print(f"  {cid}: scope={info['scope']}")
    
    with socketserver.TCPServer(("localhost", port), OAuth2Handler) as httpd:
        httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--verify", metavar="TOKEN", help="verify token")
    parser.add_argument("--gen-token", metavar="CLIENT_ID", help="generate token for client")
    args = parser.parse_args()
    
    if args.verify:
        payload = verify_token(args.verify)
        if payload:
            print(json.dumps({"valid": True, "payload": payload}, indent=2))
        else:
            print(json.dumps({"valid": False}, indent=2))
            sys.exit(1)
    
    elif args.gen_token:
        clients = load_clients()
        if args.gen_token not in clients:
            print(f"Unknown client: {args.gen_token}")
            sys.exit(1)
        token = create_token(args.gen_token, clients[args.gen_token].get("scope", "ws:chat"))
        print(token)
    
    else:
        run_server(args.port)


if __name__ == "__main__":
    main()
