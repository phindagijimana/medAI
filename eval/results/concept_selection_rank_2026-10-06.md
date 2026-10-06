# Arm E selection vs lexical retrieval (mention gold)

Scorable reachable mentions: 956. Mode: cpu.

| method | hits | R@1 |
|---|---:|---:|
| lexical rank-1 | 541 | 0.566 |
| gold in top-5 (ceiling) | 709 | 0.742 |
| token-overlap pick among top-5 (CPU stand-in) | 580 | 0.607 |

Gate (pick-from-list > lexical rank-1): **pass**.
Ceiling 0.74 vs lexical 0.56 is the room Arm E has. The CPU heuristic is not the model; `--mode gpu` is the real gate.
