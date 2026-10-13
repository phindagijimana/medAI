# LEO

**Research phenotyping for epilepsy notes** (MedAI-EPI). LEO fills a table from a clinical note: value, quote from the note, which reader said it (model, rules, or both), and whether a person should look.

> **Research use only.** Does not diagnose or recommend treatment. Tested on **synthetic notes only**. Real notes need IRB and approved compute.

Agree → accept. Clash → review; **rules** are shown (D17); the model value is kept as `alternative`. One note = one row. The **research extract** is `accepted` **and** both readers. Accepted cells are not “safe” (concordant PPV ~0.85–0.87 on the 40-letter gold).

## Start here

| Page | Use |
|---|---|
| [User guide](LEO_USER_GUIDE.md) | Commands (`bin/leo`), input/output, Validator |
| [Hosting](LEO_HOSTING.md) | Workstation vs Slurm (`--local`, `--cpu`, `--gres`) |
| [Interpreting results](INTERPRETING_RESULTS.md) | How to quote numbers; research extract ≠ reviewed |
| [Routing rules](LEO_ROUTING_RULES.md) | ACCEPT / REVIEW / REJECT |
| [Design](IMPLEMENTATION.md) | Why each step exists |
| [Weaknesses](WEAKNESSES.md) | What is still wrong |
| [Learning](ACTIVE_LEARNING_PLAN.md) | `leo learn` (does not change the extract) |

Code: [github.com/phindagijimana/medAI](https://github.com/phindagijimana/medAI).

## Commands

```bash
bin/leo install --check-only
bin/leo check                    # CPU, specialist only
bin/leo check --slurm            # Med42 on a GPU node

bin/leo phenotypes
bin/leo evidence
bin/leo batch notes.xlsx         # Slurm GPU → notes_leo.xlsx
bin/leo batch notes.xlsx --cpu   # rules only; every cell needs_review
bin/leo batch notes.xlsx --local

bin/leo start                    # web UI at /leo/ui
bin/leo review notes_leo.csv
bin/leo merge notes_leo.csv notes_leo.reviewed.csv
```

GPU extract needs Med42-8B weights, the epilepsy CDB, and a UMLS key in `.env` (never committed). CPU-only is **not** a research extract.

## What this site does not include

Paper drafts stay local. The frozen evaluation log (`EVAL_PROTOCOL_LEO.md`) and hold-out leak tables are in the repo for the study, not this operator site.
