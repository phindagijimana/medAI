# Perfect-reviewer upper bound and review workload (F-S letters, specialist + model; no human reviewers)

| model feeding LEO | letters | model alone F1 | leo_auto F1 | leo_review (draft) F1 | oracle_pick F1 | oracle - model alone | flagged claims per letter (mean / median / p90) | flagged items already right |
|---|---|---|---|---|---|---|---|---|
| L0 | 160 | 0.656 | 0.648 | 0.661 | 0.769 | +0.114 [+0.088, +0.142] | 5.86 / 5.0 / 10 | 61 of 353 (0.173) |
| L1 | 160 | 0.688 | 0.669 | 0.672 | 0.767 | +0.079 [+0.058, +0.101] | 5.51 / 5.0 / 10 | 54 of 298 (0.181) |
| L2 | 160 | 0.662 | 0.644 | 0.673 | 0.766 | +0.103 [+0.071, +0.137] | 5.47 / 5.0 / 9 | 69 of 291 (0.237) |
| H | 160 | 0.716 | 0.669 | 0.664 | 0.768 | +0.051 [+0.025, +0.079] | 5.23 / 5.0 / 9 | 45 of 252 (0.179) |
| H2 | 160 | 0.707 | 0.677 | 0.675 | 0.789 | +0.083 [+0.062, +0.104] | 5.51 / 5.0 / 9 | 52 of 298 (0.174) |
