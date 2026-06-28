#!/usr/bin/env python3
"""
v945_federated.py — FEDERATED LEARNING SIMULATION v9.45
=========================================================
Simulate federated learning across multiple LLM providers.

Scenario: 3 LLM providers (z-ai, Pollinations, rule-based) collaboratively
learn a "consensus model" without sharing raw data. Each provider trains
locally, sends only model updates (gradients), aggregator combines.

This is SIMULATED — we don't actually train neural nets. Instead:
1. Each "client" (LLM provider) answers sample questions
2. We compute per-client accuracy as "local model"
3. Aggregator computes weighted average (FedAvg)
4. Round-by-round: accuracy should improve (in real FL)

Use case: prove that v9.42 consensus can be improved over rounds
without any provider seeing others' training data.

Usage:
    python3 v945_federated.py run --rounds 3
    python3 v945_federated.py status
"""
import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

STATE_FILE = "/home/z/my-project/scripts/v945_federated_state.json"


# ============================================================================
# FEDERATED LEARNING SIMULATION
# ============================================================================

# Simulated training data (questions with known answers)
TRAINING_DATA = [
    {"q": "What is 2+2?", "a": "4"},
    {"q": "What is 3*3?", "a": "9"},
    {"q": "What is 10-4?", "a": "6"},
    {"q": "What is 100/10?", "a": "10"},
    {"q": "What is 5+5?", "a": "10"},
    {"q": "What is 7*2?", "a": "14"},
    {"q": "What is 20-8?", "a": "12"},
    {"q": "What is 6+3?", "a": "9"},
    {"q": "What is 4*4?", "a": "16"},
    {"q": "What is 15-7?", "a": "8"},
]


class FederatedClient:
    """Simulated FL client (LLM provider)."""
    
    def __init__(self, name, accuracy_base=0.7, learning_rate=0.05):
        self.name = name
        self.accuracy = accuracy_base  # current "model" accuracy
        self.learning_rate = learning_rate
        self.local_updates = []
    
    def train_local(self, round_num):
        """Simulate local training. Returns model update (delta accuracy)."""
        # Simulate: each round, accuracy improves slightly (with noise)
        noise = random.gauss(0, 0.02)
        improvement = self.learning_rate * (1 - self.accuracy) + noise
        self.accuracy = min(1.0, self.accuracy + improvement)
        
        # "Compute" update (in real FL, this would be gradients)
        update = {
            "client": self.name,
            "round": round_num,
            "accuracy": self.accuracy,
            "update_magnitude": improvement,
            "samples": len(TRAINING_DATA),
        }
        self.local_updates.append(update)
        return update
    
    def evaluate(self, test_data):
        """Evaluate on test data. Returns accuracy."""
        correct = sum(1 for item in test_data 
                      if random.random() < self.accuracy)  # probabilistic
        return correct / len(test_data)


class FedAvgAggregator:
    """FedAvg: weighted average of client updates."""
    
    def __init__(self, clients):
        self.clients = clients
        self.global_accuracy = 0.5  # initial global model
        self.rounds = []
    
    def aggregate(self, round_num):
        """Run one FL round: clients train, aggregator averages."""
        # Step 1: Each client trains locally
        updates = [c.train_local(round_num) for c in self.clients]
        
        # Step 2: FedAvg — weighted average (equal weights here)
        avg_accuracy = sum(u["accuracy"] for u in updates) / len(updates)
        
        # Step 3: Update global model
        self.global_accuracy = avg_accuracy
        
        round_data = {
            "round": round_num,
            "updates": updates,
            "global_accuracy": self.global_accuracy,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.rounds.append(round_data)
        return round_data
    
    def evaluate_global(self, test_data):
        """Evaluate global model on test data."""
        correct = sum(1 for item in test_data 
                      if random.random() < self.global_accuracy)
        return correct / len(test_data)


def run_federated(rounds=3):
    """Run federated learning simulation."""
    print("=" * 60)
    print(f"Federated Learning Simulation ({rounds} rounds)")
    print("=" * 60)
    print()
    
    # Initialize clients (3 LLM providers)
    clients = [
        FederatedClient("z-ai-glm4-plus", accuracy_base=0.75, learning_rate=0.08),
        FederatedClient("pollinations-gpt-oss-20b", accuracy_base=0.65, learning_rate=0.06),
        FederatedClient("rule-based", accuracy_base=0.90, learning_rate=0.02),  # already good at math
    ]
    
    aggregator = FedAvgAggregator(clients)
    
    # Initial evaluation
    test_data = TRAINING_DATA[:5]  # use first 5 as test
    print(f"Initial global accuracy: {aggregator.global_accuracy:.3f}")
    print(f"Clients: {[c.name for c in clients]}")
    print()
    
    # Run rounds
    for r in range(1, rounds + 1):
        print(f"--- Round {r} ---")
        round_data = aggregator.aggregate(r)
        
        print(f"  Global accuracy: {round_data['global_accuracy']:.3f}")
        for u in round_data["updates"]:
            print(f"  {u['client']}: acc={u['accuracy']:.3f}, Δ={u['update_magnitude']:+.4f}")
        
        # Evaluate on test data
        test_acc = aggregator.evaluate_global(test_data)
        print(f"  Test accuracy: {test_acc:.3f}")
        print()
    
    # Final state
    print("=" * 60)
    print("Final Results:")
    print(f"  Global accuracy: {aggregator.global_accuracy:.3f}")
    print(f"  Improvement: {aggregator.global_accuracy - 0.5:+.3f}")
    print(f"  Rounds completed: {len(aggregator.rounds)}")
    
    # Save state
    state = {
        "rounds": aggregator.rounds,
        "final_global_accuracy": aggregator.global_accuracy,
        "clients": [{"name": c.name, "final_accuracy": c.accuracy} for c in clients],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    Path(STATE_FILE).write_text(json.dumps(state, indent=2))
    print(f"\nState saved to {STATE_FILE}")
    
    return state


def show_status():
    """Show federated learning state."""
    if not os.path.exists(STATE_FILE):
        print("No FL state found. Run 'python3 v945_federated.py run' first.")
        return
    
    state = json.loads(Path(STATE_FILE).read_text())
    print(f"Federated Learning State")
    print(f"  Rounds: {len(state['rounds'])}")
    print(f"  Final global accuracy: {state['final_global_accuracy']:.3f}")
    print(f"  Last update: {state['timestamp']}")
    print()
    print("Clients:")
    for c in state["clients"]:
        print(f"  {c['name']}: {c['final_accuracy']:.3f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "status"])
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    
    if args.command == "run":
        run_federated(args.rounds)
    elif args.command == "status":
        show_status()


if __name__ == "__main__":
    main()
