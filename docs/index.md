# LEO

**Research phenotyping for epilepsy notes** (MedAI-EPI).

Full documentation at [https://medai.readthedocs.io](https://medai.readthedocs.io).

> **Research use only.** Does not diagnose or recommend treatment. Tested on **synthetic notes only**. Real notes need IRB and approved compute.

## About

LEO reads a clinical note and fills a phenotype table: value, quote from the note, which reader said it (model, rules, or both), and whether a person should look.

The main features of this software are:

1. **Two readers, one table.** Constrained Med42-8B plus ExECT-style rules (EpExtra). Agree → accept. Clash → review; the **rules** are shown (D17); the model value is kept as `alternative`.
2. **One note = one row.** Roll-up is optional and is not the extract. The research extract is `accepted` **and** both readers.
3. **A Validator, not a chat.** Accept / Correct / Deny / add missed values. `leo learn` scores routing later; it does not change the extract.

Accepted cells are not “safe” (concordant PPV ~0.85–0.87 on the 40-letter gold). CPU-only has one reader and is **not** a research extract.

Code: [github.com/phindagijimana/medAI](https://github.com/phindagijimana/medAI).

## Documentation

| Page | Use |
|---|---|
| [Installation](LEO_HOSTING.md) | Workstation, Slurm, weights, UMLS |
| [Quick start](QUICKSTART.md) | `bin/leo check` and a first batch |
| [Usage](LEO_USER_GUIDE.md) | Commands, input/output, Validator |
| [Interpreting results](INTERPRETING_RESULTS.md) | How to quote numbers |
| [Routing rules](LEO_ROUTING_RULES.md) | ACCEPT / REVIEW / REJECT |
| [Design](IMPLEMENTATION.md) | Why each step exists |
| [Weaknesses](WEAKNESSES.md) | What is still wrong |
| [Learning](ACTIVE_LEARNING_PLAN.md) | `leo learn` (does not change the extract) |

## What this site does not include

Paper drafts stay local. The frozen evaluation log and hold-out leak tables are in the repo for the study, not this operator site.
