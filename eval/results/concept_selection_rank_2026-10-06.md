# Arm E selection vs lexical retrieval (mention gold)

Scorable reachable mentions: 956. Mode: cpu.

| method | hits | R@1 |
|---|---:|---:|
| lexical rank-1 | 541 | 0.566 |
| gold in top-5 (ceiling) | 709 | 0.742 |
| token-overlap pick among top-5 (CPU stand-in) | 580 | 0.607 |

Gate (pick-from-list > lexical rank-1): **pass**.
Ceiling 0.74 vs lexical 0.56 is the room Arm E has. The CPU heuristic is not the model; `--mode gpu` is the real gate.


Lexical rank-1 misses: 415 (in top-5: 168; not in top-5: 247).
Wrote eval/results/concept_selection_rank_2026-10-06.misses.csv.

Most frequent missed mentions:
- mri (68)
- eeg (61)
- generalised tonic clonic seizures (41)
- focal to bilateral convulsive seizures (19)
- sodium valproate (16)
- generalised tonic clonic seizure (11)
- epileptic seizures (10)
- jme (6)
- mri brain (5)
- eegs (5)
- generalised tonic chronic seizures (4)
- primary generalised epilepsy (4)
- normal mri (4)
- tonic clonic seizures (4)
- focal (4)

Most frequent wrong rank-1 labels:
- mri of brain (68)
- electroencephalogram (61)
- clonic seizure (55)
- valproate (39)
- right and left (22)
- mri of brain normal (16)
- generalized onset tonic-clonic epileptic seizure (14)
- seizure (13)
- tonic (12)
- temporal lobe structure (11)
- carbamazepine (6)
- levetiracetam (6)
- generalized epilepsy (5)
- lamotrigine (5)
- occipital lobe structure (4)
