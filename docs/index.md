# LEO

**Research phenotyping for epilepsy notes** (MedAI-EPI).

Full documentation at [https://medai.readthedocs.io](https://medai.readthedocs.io).

> **Research use only.** Does not diagnose or recommend treatment. Tested on **synthetic notes only**. Real notes need IRB and approved compute.

## What LEO does

LEO (Language, EpExtra, Ontology) is a research tool for epilepsy clinic letters. It reads a note and fills a phenotype table: seizure and epilepsy type, medications and status, EEG and MRI cues, and related fields. Every cell carries a value, a quote from the note, which reader produced it, and whether a person should look. The aim is a table a study can defend — agreed cells kept, clashes visible — not a silent guess at a complete phenotype.

A letter often supports more than one reading of the same sentence (current versus prior, plan versus fact, the patient’s drug versus family history). LEO therefore runs two different readers: a constrained clinical language model (Med42-8B) and deterministic ExECT-style rules. Cells where they agree become the research extract. Cells where they clash go to a review queue; the rules value is shown and the model value is kept as an alternative. An ontology layer can attach published codes after extract. It does not vote, and it is not used to raise precision.

This has been tested on **synthetic** clinician-authored letters only. It does not diagnose or recommend treatment. Accepted cells still miss gold about one time in six or seven (concordant PPV 71/82 = 0.866 on the 40-letter set). CPU-only runs have one reader and are not a research extract. Why the three parts exist: [Theory and Science](THEORY.md). How to quote a number: [Interpreting results](INTERPRETING_RESULTS.md).

## In practice

1. **Two readers, one table.** Constrained Med42-8B plus ExECT-style rules (EpExtra). Agree → accept. Clash → review; the **rules** are shown (D17); the model value is kept as `alternative`.
2. **One note = one row.** Roll-up is optional and is not the extract. The research extract is `accepted` **and** both readers.
3. **A Validator, not a chat.** Accept / Correct / Deny / add missed values. `leo learn` scores routing later; it does not change the extract.

Code: [github.com/phindagijimana/medAI](https://github.com/phindagijimana/medAI).

## Documentation

| Page | Use |
|---|---|
| [Installation](LEO_HOSTING.md) | Workstation, Slurm, weights, UMLS |
| [Quick start](QUICKSTART.md) | `bin/leo check` and a first batch |
| [Usage](LEO_USER_GUIDE.md) | Commands, input/output, Validator |
| [Theory and Science](THEORY.md) | Why L, E, and O — and why they are not voted |
| [Literature](LITERATURE.md) | Papers LEO cites |
| [Interpreting results](INTERPRETING_RESULTS.md) | How to quote numbers |
| [Routing rules](LEO_ROUTING_RULES.md) | ACCEPT / REVIEW / REJECT |
| [Design](IMPLEMENTATION.md) | Why each step exists |
| [Weaknesses](WEAKNESSES.md) | What is still wrong |
| [Learning](ACTIVE_LEARNING_PLAN.md) | `leo learn` (does not change the extract) |

## What this site does not include

Paper drafts stay local. The frozen evaluation log and hold-out leak tables are in the repo for the study, not this operator site.
