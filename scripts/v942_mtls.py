#!/usr/bin/env python3
"""
v942_mtls.py — mTLS FOR CLUSTER INTERNAL v9.42
================================================
Mutual TLS for daemon cluster internal communication.

Generates self-signed CA + client/server certs.
Cluster workers communicate via TLS with cert verification.

Use case:
- Master daemon → worker daemon calls (internal, mTLS)
- Worker → worker (if they share work)

This prevents MITM attacks within the cluster.

Usage:
    python3 v942_mtls.py --gen-ca          # generate CA
    python3 v942_mtls.py --gen-cert master  # generate cert for 'master'
    python3 v942_mtls.py --gen-cert worker0
    python3 v942_mtls.py --verify master    # verify cert
    python3 v942_mtls.py --status           # show cert inventory
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

CERT_DIR = "/home/z/my-project/scripts/v942_certs"
CA_CERT = f"{CERT_DIR}/ca.pem"
CA_KEY = f"{CERT_DIR}/ca-key.pem"


def ensure_cert_dir():
    Path(CERT_DIR).mkdir(parents=True, exist_ok=True)


def gen_ca():
    """Generate self-signed CA."""
    ensure_cert_dir()
    if os.path.exists(CA_CERT):
        print(f"CA already exists: {CA_CERT}")
        return
    
    print("Generating CA...")
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", CA_KEY,
        "-out", CA_CERT,
        "-days", "365",
        "-subj", "/CN=v9.42-cluster-ca",
        "-addext", "basicConstraints=critical,CA:TRUE",
    ], check=True, capture_output=True)
    Path(CA_KEY).chmod(0o600)
    print(f"CA cert: {CA_CERT}")
    print(f"CA key:  {CA_KEY}")


def gen_cert(name):
    """Generate cert signed by CA for given name (master, worker0, etc.)."""
    ensure_cert_dir()
    if not os.path.exists(CA_CERT):
        gen_ca()
    
    cert_path = f"{CERT_DIR}/{name}.pem"
    key_path = f"{CERT_DIR}/{name}-key.pem"
    csr_path = f"{CERT_DIR}/{name}.csr"
    
    if os.path.exists(cert_path):
        print(f"Cert already exists: {cert_path}")
        return
    
    print(f"Generating cert for '{name}'...")
    # 1. Generate private key + CSR
    subprocess.run([
        "openssl", "req", "-newkey", "rsa:2048", "-nodes",
        "-keyout", key_path,
        "-out", csr_path,
        "-subj", f"/CN=v9.42-{name}",
    ], check=True, capture_output=True)
    Path(key_path).chmod(0o600)
    
    # 2. Sign CSR with CA
    subprocess.run([
        "openssl", "x509", "-req",
        "-in", csr_path,
        "-CA", CA_CERT,
        "-CAkey", CA_KEY,
        "-CAcreateserial",
        "-out", cert_path,
        "-days", "365",
        "-extfile", "-",  # read extensions from stdin
    ], check=True, capture_output=True, input=f"subjectAltName=DNS:localhost\nextendedKeyUsage=serverAuth,clientAuth\n".encode())
    
    # Cleanup CSR
    os.unlink(csr_path)
    
    print(f"Cert: {cert_path}")
    print(f"Key:  {key_path}")


def verify_cert(name):
    """Verify cert against CA."""
    cert_path = f"{CERT_DIR}/{name}.pem"
    if not os.path.exists(cert_path):
        print(f"Cert not found: {cert_path}")
        return False
    
    result = subprocess.run([
        "openssl", "verify",
        "-CAfile", CA_CERT,
        cert_path,
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"OK: {name} cert verified")
        # Show cert details
        details = subprocess.run([
            "openssl", "x509", "-in", cert_path, "-noout", "-subject", "-dates",
        ], capture_output=True, text=True)
        print(details.stdout)
        return True
    else:
        print(f"FAIL: {name} cert verification failed: {result.stderr}")
        return False


def cert_inventory():
    """Show all certs in inventory."""
    if not os.path.exists(CERT_DIR):
        print("No cert directory")
        return
    
    certs = sorted(Path(CERT_DIR).glob("*.pem"))
    print(f"Certificate inventory ({len(certs)} files in {CERT_DIR}):")
    print()
    for c in certs:
        if "ca-key" in c.name:
            continue
        size = c.stat().st_size
        print(f"  {c.name:<30} {size:>6} bytes")
    
    # Verify each non-CA cert
    print()
    print("Verification:")
    for c in certs:
        if c.name in ("ca.pem", "ca-key.pem"):
            continue
        if c.name.endswith("-key.pem"):
            continue
        name = c.name.replace(".pem", "")
        verify_cert(name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gen-ca", action="store_true")
    parser.add_argument("--gen-cert", metavar="NAME")
    parser.add_argument("--verify", metavar="NAME")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    
    if args.gen_ca:
        gen_ca()
    elif args.gen_cert:
        gen_cert(args.gen_cert)
    elif args.verify:
        verify_cert(args.verify)
    elif args.status:
        cert_inventory()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
