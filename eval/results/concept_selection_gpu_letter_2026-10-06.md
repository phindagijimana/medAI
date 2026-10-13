# Arm E selection vs lexical retrieval (mention gold)

Scorable reachable mentions: 956. Mode: gpu.

| method | hits | R@1 |
|---|---:|---:|
| lexical rank-1 | 541 | 0.566 |
| gold in top-5 (ceiling) | 709 | 0.742 |
| Arm E selector | 316 | 0.331 |

Gate (pick-from-list > lexical rank-1): **fail**.
Ceiling 0.74 vs lexical 0.56 is the room Arm E has. The CPU heuristic is not the model; `--mode gpu` is the real gate.
