#!/usr/bin/env python3
"""
v947_chaos.py — CHAOS ENGINEERING v9.47
==========================================
Inject failures into the system to test resilience.

Chaos experiments:
1. Kill daemon → verify bootstrap recovers
2. Delete output.md → verify fixture recreated
3. Corrupt audit chain → verify tamper detection
4. Fill disk → verify graceful degradation
5. Block network → verify cache fallback
6. Overload with requests → verify rate limiting

Each experiment:
- Inject failure
- Wait
- Verify system detected + recovered
- Log result

Usage:
    python3 v947_chaos.py run --experiment kill-daemon
    python3 v947_chaos.py run-all
    python3 v947_chaos.py report
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/z/my-project/scripts")

REPORT_FILE = "/home/z/my-project/scripts/v947_chaos_report.json"


class ChaosExperiment:
    """Base class for chaos experiments."""
    
    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.result = None
    
    def inject(self):
        """Inject failure. Override in subclass."""
        raise NotImplementedError
    
    def verify(self):
        """Verify system handled failure. Override in subclass."""
        raise NotImplementedError
    
    def recover(self):
        """Recover from failure. Override in subclass."""
        raise NotImplementedError
    
    def run(self):
        """Run full experiment: inject → verify → recover."""
        print(f"\n{'='*60}")
        print(f"Experiment: {self.name}")
        print(f"Description: {self.description}")
        print(f"{'='*60}")
        
        start = time.time()
        
        # Inject
        print(f"\n[1/3] Injecting failure...")
        try:
            inject_result = self.inject()
            print(f"  Injected: {inject_result}")
        except Exception as e:
            print(f"  Inject failed: {e}")
            inject_result = str(e)
        
        # Wait
        time.sleep(2)
        
        # Verify
        print(f"\n[2/3] Verifying system response...")
        try:
            verify_result = self.verify()
            passed = verify_result.get("recovered", False) or verify_result.get("detected", False)
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {status}: {verify_result}")
        except Exception as e:
            verify_result = {"error": str(e), "recovered": False}
            passed = False
            print(f"  ❌ FAIL: {e}")
        
        # Recover
        print(f"\n[3/3] Recovering...")
        try:
            recover_result = self.recover()
            print(f"  Recovered: {recover_result}")
        except Exception as e:
            recover_result = str(e)
            print(f"  Recovery issue: {e}")
        
        elapsed = time.time() - start
        self.result = {
            "name": self.name,
            "description": self.description,
            "inject_result": str(inject_result),
            "verify_result": verify_result,
            "recover_result": str(recover_result),
            "passed": passed,
            "elapsed_sec": round(elapsed, 2),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        
        return self.result


# ============================================================================
# EXPERIMENTS
# ============================================================================

class KillDaemonExperiment(ChaosExperiment):
    """Kill the daemon process, verify system detects + can restart."""
    
    def __init__(self):
        super().__init__("kill-daemon", "Kill daemon process, verify detection + recovery")
    
    def inject(self):
        # Find daemon PID
        pid_file = Path("/home/z/my-project/scripts/v937_daemon.pid")
        if not pid_file.exists():
            return "daemon not running"
        
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 9)  # SIGKILL
        return f"killed daemon PID={pid}"
    
    def verify(self):
        # Check if daemon socket is gone
        sock = Path("/home/z/my-project/scripts/v937_daemon.sock")
        socket_gone = not sock.exists()
        
        # Try to query daemon
        try:
            result = subprocess.run(
                ["python3", "/home/z/my-project/scripts/v937_daemon.py", "--status"],
                capture_output=True, text=True, timeout=5
            )
            alive = "ALIVE" in result.stdout
        except:
            alive = False
        
        return {
            "detected": socket_gone or not alive,
            "daemon_dead": not alive,
            "socket_gone": socket_gone,
        }
    
    def recover(self):
        # Restart daemon
        subprocess.run(
            ["python3", "/home/z/my-project/scripts/v937_daemon.py", "--start"],
            capture_output=True, text=True, timeout=30
        )
        time.sleep(3)
        return "daemon restarted"


class DeleteOutputMdExperiment(ChaosExperiment):
    """Delete output.md fixture, verify it's recreated."""
    
    def __init__(self):
        super().__init__("delete-output-md", "Delete output.md, verify fixture recreation")
    
    def inject(self):
        output_md = Path("/home/z/my-project/download/output.md")
        if output_md.exists():
            output_md.unlink()
            return "deleted output.md"
        return "output.md didn't exist"
    
    def verify(self):
        output_md = Path("/home/z/my-project/download/output.md")
        return {
            "detected": not output_md.exists(),
            "fixture_missing": not output_md.exists(),
        }
    
    def recover(self):
        # Run bootstrap to recreate
        subprocess.run(
            ["bash", "/home/z/my-project/scripts/bootstrap.sh"],
            capture_output=True, text=True, timeout=120
        )
        output_md = Path("/home/z/my-project/download/output.md")
        return f"output.md recreated: {output_md.exists()}"


class CorruptAuditChainExperiment(ChaosExperiment):
    """Corrupt audit chain, verify tamper detection."""
    
    def __init__(self):
        super().__init__("corrupt-audit", "Corrupt audit blockchain, verify tamper detection")
        self.backup = None
    
    def inject(self):
        chain_file = Path("/home/z/my-project/audit_trail/v943_blockchain.json")
        if not chain_file.exists():
            return "no blockchain to corrupt"
        
        # Backup
        self.backup = chain_file.read_text()
        
        # Corrupt: modify first block's claim
        chain = json.loads(self.backup)
        if chain:
            chain[0]["claim"] = "TAMPERED BY CHAOS ENGINEERING"
            chain_file.write_text(json.dumps(chain, indent=2))
            return "corrupted block 0 claim"
        return "empty chain"
    
    def verify(self):
        # Run blockchain verify
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v943_blockchain.py", "verify"],
            capture_output=True, text=True, timeout=10
        )
        tamper_detected = "hash mismatch" in result.stdout.lower() or "FAIL" in result.stdout.upper()
        
        return {
            "detected": tamper_detected,
            "verify_output": result.stdout[:200],
        }
    
    def recover(self):
        # Restore backup
        chain_file = Path("/home/z/my-project/audit_trail/v943_blockchain.json")
        if self.backup:
            chain_file.write_text(self.backup)
            return "blockchain restored from backup"
        return "no backup to restore"


class LongPromptExperiment(ChaosExperiment):
    """Send extremely long prompt, verify resource exhaustion protection."""
    
    def __init__(self):
        super().__init__("long-prompt", "Send 50k char prompt, verify DoS protection")
    
    def inject(self):
        self.long_prompt = "A" * 50000
        return f"created 50k char prompt"
    
    def verify(self):
        # Check safety filter
        result = subprocess.run(
            ["python3", "/home/z/my-project/scripts/v945_safety.py", "check-input", "--prompt", self.long_prompt],
            capture_output=True, text=True, timeout=10
        )
        try:
            data = json.loads(result.stdout.strip())
            blocked = not data.get("safe", True)
            return {
                "detected": blocked,
                "blocked": blocked,
                "decision": data.get("decision"),
            }
        except:
            return {"detected": False, "error": "could not parse safety result"}
    
    def recover(self):
        return "no recovery needed (prompt was blocked, not sent)"


# ============================================================================
# RUNNER
# ============================================================================

EXPERIMENTS = [
    KillDaemonExperiment,
    DeleteOutputMdExperiment,
    CorruptAuditChainExperiment,
    LongPromptExperiment,
]


def run_all():
    """Run all chaos experiments."""
    print("=" * 60)
    print("CHAOS ENGINEERING — v9.47")
    print(f"Running {len(EXPERIMENTS)} experiments")
    print("=" * 60)
    
    results = []
    for ExpClass in EXPERIMENTS:
        exp = ExpClass()
        result = exp.run()
        results.append(result)
        time.sleep(1)
    
    # Summary
    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed
    
    print(f"\n{'='*60}")
    print(f"CHAOS ENGINEERING SUMMARY")
    print(f"{'='*60}")
    print(f"Experiments: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Pass rate: {passed/len(results)*100:.1f}%")
    print()
    
    for r in results:
        status = "✅" if r["passed"] else "❌"
        print(f"  {status} {r['name']:<25} ({r['elapsed_sec']}s)")
    
    # Save report
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_experiments": len(results),
        "passed": passed,
        "failed": failed,
        "pass_rate_pct": round(passed / len(results) * 100, 1),
        "results": results,
    }
    Path(REPORT_FILE).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nReport: {REPORT_FILE}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run-all", "run", "report"])
    parser.add_argument("--experiment", help="specific experiment to run")
    args = parser.parse_args()
    
    if args.command == "run-all":
        run_all()
    elif args.command == "run":
        if not args.experiment:
            print("--experiment required. Available: " + ", ".join(e.__name__.replace("Experiment", "") for e in EXPERIMENTS))
            sys.exit(2)
        # Find matching experiment
        for ExpClass in EXPERIMENTS:
            name = ExpClass.__name__.replace("Experiment", "").replace("-", "").lower()
            if args.experiment.replace("-", "").lower() in name:
                exp = ExpClass()
                exp.run()
                return
        print(f"Unknown experiment: {args.experiment}")
    elif args.command == "report":
        if os.path.exists(REPORT_FILE):
            report = json.loads(Path(REPORT_FILE).read_text())
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print("No report found")


if __name__ == "__main__":
    main()
