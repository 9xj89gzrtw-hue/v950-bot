#!/usr/bin/env python3
"""
v945_federated.py — FEDERATED LEARNING SIMULATION v9.45
=========================================================
Simulate federated learning: multiple "clients" (LLM providers)
collaboratively learn without sharing raw data.

Scenario: 3 LLM providers (z-ai, Pollinations, rule-based) each have
local prompt-response pairs. They want to build a shared "consensus model"
WITHOUT sharing their training data.

Federated Averaging (FedAvg):
1. Each client trains locally on its data
2. Each client sends model updates (gradients) to server
3. Server averages updates
4. Server sends averaged update back to clients
5. Repeat

Our simulation:
- "Model" = simple weight vector (3 dimensions)
- "Training" = adjust weights based on local data
- "Data" = simulated prompt-response pairs
- Differential privacy: add noise to updates (DP-SGD)

Usage:
    python3 v945_federated.py simulate --rounds 5
    python3 v945_federated.py demo
"""
import argparse
import json
import random
import sys
from pathlib import Path


# ============================================================================
# SIMULATED CLIENTS (LLM providers)
# ============================================================================

class FederatedClient:
    """Simulated LLM provider with local data."""
    
    def __init__(self, name, data, initial_weights=None):
        self.name = name
        self.data = data  # list of (input, target) pairs
        self.weights = initial_weights or [0.0, 0.0, 0.0]
        self.update_count = 0
    
    def local_train(self, epochs=1, learning_rate=0.1, dp_noise=0.0):
        """Train locally on own data. Returns weight update (delta)."""
        old_weights = self.weights.copy()
        
        for _ in range(epochs):
            for x, y in self.data:
                # Simple gradient descent on squared error
                # loss = (w·x - y)^2
                # d_loss/d_w = 2 * (w·x - y) * x
                prediction = sum(w * xi for w, xi in zip(self.weights, x))
                error = prediction - y
                gradient = [2 * error * xi for xi in x]
                
                # Update weights
                for i in range(len(self.weights)):
                    self.weights[i] -= learning_rate * gradient[i]
        
        # Add DP noise (DP-SGD)
        if dp_noise > 0:
            self.weights = [
                w + random.gauss(0, dp_noise) for w in self.weights
            ]
        
        # Return update (delta)
        delta = [new - old for new, old in zip(self.weights, old_weights)]
        self.update_count += 1
        return delta
    
    def evaluate(self, test_data):
        """Evaluate on test data. Returns MSE."""
        total_error = 0
        for x, y in test_data:
            prediction = sum(w * xi for w, xi in zip(self.weights, x))
            total_error += (prediction - y) ** 2
        return total_error / len(test_data) if test_data else 0


# ============================================================================
# FEDERATED SERVER
# ============================================================================

class FederatedServer:
    """Coordinates federated learning."""
    
    def __init__(self, initial_weights=None):
        self.global_weights = initial_weights or [0.0, 0.0, 0.0]
        self.rounds_completed = 0
        self.history = []
    
    def aggregate(self, client_updates):
        """FedAvg: average client updates."""
        if not client_updates:
            return self.global_weights
        
        # Average updates
        avg_delta = [0.0] * len(self.global_weights)
        for delta in client_updates:
            for i in range(len(avg_delta)):
                avg_delta[i] += delta[i]
        
        avg_delta = [d / len(client_updates) for d in avg_delta]
        
        # Apply to global weights
        self.global_weights = [
            w + d for w, d in zip(self.global_weights, avg_delta)
        ]
        
        self.rounds_completed += 1
        return self.global_weights
    
    def distribute(self, clients):
        """Send global weights to all clients."""
        for client in clients:
            client.weights = self.global_weights.copy()


def simulate_federated(rounds=5, dp_noise=0.0, verbose=True):
    """Run federated learning simulation."""
    # Generate synthetic data for 3 clients
    # Each client has different distribution (non-IID)
    random.seed(42)
    
    # Client 1: z-ai (data centered around [1, 0, 0])
    client1_data = [([1.0, random.gauss(0, 0.1), random.gauss(0, 0.1)], 1.0) for _ in range(20)]
    
    # Client 2: Pollinations (data centered around [0, 1, 0])
    client2_data = [([random.gauss(0, 0.1), 1.0, random.gauss(0, 0.1)], 1.0) for _ in range(20)]
    
    # Client 3: rule-based (data centered around [0, 0, 1])
    client3_data = [([random.gauss(0, 0.1), random.gauss(0, 0.1), 1.0], 1.0) for _ in range(20)]
    
    clients = [
        FederatedClient("z-ai", client1_data),
        FederatedClient("pollinations", client2_data),
        FederatedClient("rule-based", client3_data),
    ]
    
    server = FederatedServer()
    
    # Test data (held out)
    test_data = [([1.0, 0.0, 0.0], 1.0), ([0.0, 1.0, 0.0], 1.0), ([0.0, 0.0, 1.0], 1.0)]
    
    if verbose:
        print(f"=== Federated Learning Simulation ===")
        print(f"Clients: {[c.name for c in clients]}")
        print(f"Rounds: {rounds}")
        print(f"DP noise: {dp_noise}")
        print(f"Initial weights: {server.global_weights}")
        print()
    
    for round_num in range(1, rounds + 1):
        # Distribute global weights to clients
        server.distribute(clients)
        
        # Each client trains locally
        updates = []
        round_info = {"round": round_num, "clients": []}
        for client in clients:
            delta = client.local_train(epochs=1, learning_rate=0.1, dp_noise=dp_noise)
            updates.append(delta)
            
            # Evaluate client locally
            local_mse = client.evaluate(client.data)
            round_info["clients"].append({
                "name": client.name,
                "local_mse": round(local_mse, 4),
                "update_count": client.update_count,
            })
        
        # Server aggregates
        server.aggregate(updates)
        
        # Evaluate global model
        # Create temp client with global weights for evaluation
        temp_client = FederatedClient("global", [])
        temp_client.weights = server.global_weights
        global_mse = temp_client.evaluate(test_data)
        
        round_info["global_weights"] = [round(w, 4) for w in server.global_weights]
        round_info["global_mse"] = round(global_mse, 4)
        
        server.history.append(round_info)
        
        if verbose:
            print(f"Round {round_num}:")
            print(f"  Global weights: {[round(w, 4) for w in server.global_weights]}")
            print(f"  Global MSE: {global_mse:.4f}")
            for c_info in round_info["clients"]:
                print(f"  {c_info['name']}: local MSE={c_info['local_mse']}")
            print()
    
    return {
        "rounds_completed": server.rounds_completed,
        "final_weights": [round(w, 4) for w in server.global_weights],
        "final_mse": round(global_mse, 4),
        "dp_noise": dp_noise,
        "history": server.history,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["simulate", "demo"])
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--dp-noise", type=float, default=0.0, help="DP noise (0=off, 0.1=moderate)")
    args = parser.parse_args()
    
    if args.command == "simulate":
        result = simulate_federated(rounds=args.rounds, dp_noise=args.dp_noise)
        # Don't print full history, just summary
        summary = {k: v for k, v in result.items() if k != "history"}
        print(json.dumps(summary, indent=2))
    
    elif args.command == "demo":
        print("=== FedAvg without DP ===")
        r1 = simulate_federated(rounds=5, dp_noise=0.0)
        print(f"\nFinal MSE (no DP): {r1['final_mse']}")
        
        print("\n=== FedAvg with DP (noise=0.1) ===")
        r2 = simulate_federated(rounds=5, dp_noise=0.1)
        print(f"\nFinal MSE (with DP): {r2['final_mse']}")
        
        print("\n=== Comparison ===")
        print(f"Without DP: weights={r1['final_weights']}, MSE={r1['final_mse']}")
        print(f"With DP:    weights={r2['final_weights']}, MSE={r2['final_mse']}")
        print(f"DP cost: MSE increased by {r2['final_mse'] - r1['final_mse']:.4f}")


if __name__ == "__main__":
    main()
