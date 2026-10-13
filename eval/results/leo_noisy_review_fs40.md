# Noisy-reviewer curve (F-S letters; stored L1C; no GPU)

`leo-v0.9` rematch. A reviewer may only pick among values the two readers already produced. With probability *p* they pick a wrong available candidate. *p* = 0 is that pick with no noise — **not** a replacement for the frozen extras oracle F1 **0.796** (`leo_paper_extras_fs40.md`). This rematch’s *p* = 0 is 0.858 (more gold-`unknown` cells are now REVIEW via `unknown_silent`). Not minutes. Not Loop A. Do not retitle the paper on these F1s.

| model | letters | p(error) | P | R | F1 |
|---|---:|---:|---:|---:|---:|
| L1C | 40 | 0.00 | 0.896 | 0.823 | 0.858 |
| L1C | 40 | 0.10 | 0.894 | 0.803 | 0.846 |
| L1C | 40 | 0.25 | 0.868 | 0.803 | 0.834 |
| L1C | 40 | 0.50 | 0.788 | 0.707 | 0.746 |
| L1C | 40 | 1.00 | 0.634 | 0.578 | 0.605 |
