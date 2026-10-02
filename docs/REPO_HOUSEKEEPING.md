# Repository housekeeping: findings and proposed commit plan

Status: proposal. **Nothing has been committed.** Do not commit until the owner approves the
groups in §3.

## 1. Findings

| # | Finding | Risk | Proposed fix |
|---|---|---|---|
| H1 | `references/` is gitignored, but `services/curated_code_audit.py`, `tests/test_curated_codes.py`, `scripts/apply_curated_code_corrections.py` and `scripts/audit_curated_codes.py` read `references/curated_code_{known_issues.json,reviewed.csv,corrections.csv}`. | A fresh clone has no such files, so the audit and its tests fail or silently skip. | Move the three curated-code files to a tracked directory (suggest `data/curated/`), update the four paths, keep `references/` ignored (it also holds study-only ExECT material). **Done:** files are in `data/curated/`, paths updated, `references/curated_code_*` removed. |
| H2 | `curated_code_corrections.csv` (94 lines) and `curated_code_reviewed.csv` quote SNOMED CT descriptions in the `note` / `reason` columns (for example the preferred term of a replaced code). SNOMED CT is UMLS-licensed and must not be redistributed. | Publishing quoted terms would breach the licence terms we accepted. | Before moving them out of `references/`, scrub `note`/`reason` to remove SNOMED-quoted text (keep code numbers, source and a short reason in our own words). Keep an unscrubbed copy under the gitignored `data/ontologies/`. **Done:** quoted terms replaced by "[term]" in `data/curated/`; originals in `data/ontologies/curated_unscrubbed/` (ignored). |
| H3 | `references/exect_v2_*.csv` derive from ExECT-V2 files that are study-only. | Redistribution terms of ExECT-V2 are not recorded here. | Keep ignored. State in `docs/EXECT_V2_STUDY.md` that only metadata is described there (already stated). |
| H4 | `eval/results/concept_retrieval*.{md,json}` quote SNOMED / RxNorm labels. | Same licence risk. | **Fixed:** ignored in `.gitignore`. Only aggregate numbers go in tracked docs. |
| H5 | Core chain code is untracked: `routes/chain_extract.py`, `routes/review_ui.py`, `services/chain_llm.py`, `ft_extract.py`, `flat_extract.py`, `ontology_loaders.py`, `ontology_releases.py`, `curated_code_audit.py`, `rules/asm_lexicon.py`, plus `app.py` (modified) registers them. | A commit that includes `app.py` without them breaks the app (blueprint registration is wrapped in try/except, so it fails silently with a log warning). | Commit in the dependency order in §3. |
| H6 | `slurm-151964.out` and `logs/*` are untracked job output. | Logs may contain note text; they were produced when PyRuSH wrote every token at DEBUG. | `slurm-*.out` now ignored. **Fixed at source:** `rules/context_config.py` silences loguru unless `MEDAI_DEBUG_NLP=1`. Review `logs/` before any publication; do not commit them. |
| H7 | `Chain_System/chain-of-three-compendium (1).pdf` is untracked. | Third-party PDF; redistribution rights unknown. | Do not commit unless the source and licence are recorded. |
| H8 | Run manifests (`data/run_manifests_*`, about 60 directories) are untracked. They hold model outputs on F-S letters, MTSamples (no licence) and synthetic notes. | MTSamples text must not be redistributed (`.gitignore` already says so for its raw copy); manifests may embed raw note text or quotes. | Decide per directory: synthetic and F-S (CC-BY) manifests may be tracked or archived (Zenodo); anything derived from MTSamples stays ignored. Add explicit ignore rules for `run_manifests_medcat_rules_mtsamples_*`. |
| H9 | The Flask app (`venv`, py3.9, no MedCAT) and the chain (`venv-medcat`, py3.11, no Flask) live in different environments. The chain routes need both in one process. | `/extract/chain` cannot run from either venv as installed. | Build one environment with both (needs a network install; blocked in this sandbox), or run the app from `venv-medcat` after adding `flask`, `flask-cors`. Smoke tests here borrowed Flask from `venv` through `PYTHONPATH` (see §4). |
| H10 | The `bin/medai-epi` CLI has no `chain` or `review` subcommand. | Reviewers must use the HTTP API or the UI; the CLI only reaches the older `/extract` endpoints. | Add `medai-epi chain` and `medai-epi review` as thin wrappers over the routes (small change). **Done:** `medai-epi chain` and `medai-epi review list|resolve` in `scripts/medai_epi_cli.py`, checked against a live server in `scripts/smoke_chain_http.py`. |

## 2. What was verified in this pass

See §4. After `leo-v0.5` (2026-10-01): full suite 275 passed under `venv-medcat`, and
`scripts/smoke_chain_http.py` all checks passed. Rerun both before any commit.

## 3. Proposed commit groups (in dependency order)

1. **Ontology resources:** `scripts/fetch_ontologies.py`, `services/ontology_{loaders,releases}.py`,
   `data/ontologies/MANIFEST.json`, `.gitignore`, `docs/ontology_resources.md`,
   `docs/ONTOLOGY_SOURCES.md`, `tests/test_ontology_candidates.py`, `services/ontology_candidates.py`.
2. **Curated codes (after H1 and H2):** `services/curated_code_audit.py`, the audit/apply scripts,
   moved and scrubbed CSV/JSON, `tests/test_curated_codes.py`, `rules/epilepsy_ontology*.py`.
3. **ASM lexicon:** `scripts/build_asm_lexicon.py`, `rules/asm_lexicon.py`, `rules/fields/medication.py`.
4. **MedCAT / MetaCAT evaluation:** `docs/METACAT_EVAL.md`, `docs/MedCAT.md`, `scripts/train_metacat.py`,
   `services/metacat_backend.py`, the enrich/apply scripts, `scripts/run_medcat_rules_on_corpus.py`.
5. **Chain core:** `schema/claim.py`, `services/ledger.py`, `services/chain_pipeline.py`,
   `routes/chain_extract.py`, `routes/review_ui.py`, `routes/extract_ui.py`, `app.py`,
   `scripts/extract_chain_cli.py`, `rules/context_config.py`.
6. **LEO LLM channel:** `services/chain_llm.py`, `ft_extract.py`, `flat_extract.py`, `med_context.py`,
   the `run_med42_*` runners and SLURM scripts, `tests/test_{chain_llm,ft_extract,flat_extract,leo_v04,leo_rescue}.py`.
7. **Evaluation and protocol:** `scripts/score_leo_vs_fs_gold.py`, `scripts/score_leo_vs_synth_gold.py`,
   `scripts/diag_synth_claim_errors.py`, `services/synth_eval.py`, `tests/test_synth_eval.py`, `docs/LEO_ROUTING_RULES.md`, `scripts/eval_concept_retrieval.py`,
   `scripts/smoke_chain_http.py`, `docs/EVAL_PROTOCOL_LEO.md`, `docs/CONCEPT_GOLD_SET.md`,
   `docs/SCOPE_DECISIONS.md`, `docs/US_ANNOTATION_PLAN.md`, `docs/EXECT_EPEXTRA_PARITY.md`,
   `docs/REPO_HOUSEKEEPING.md`, `docs/CHAIN_OF_THREE_ALIGNMENT.md`.
8. **Data and manifests:** only after H8 is decided; separate commit or an archive release.

Before each commit: run the full `pytest tests/` under `venv-medcat`; run
`git diff --cached --stat` and confirm no file under `data/ontologies/` (except
`MANIFEST.json`) and no `eval/results/concept_retrieval*` is staged.

## 4. Smoke tests run (2026-10-01)

| test | command | result |
|---|---|---|
| Existing HTTP surface (`/extract/*`) | `PYTHONPATH=/tmp/flask_site venv-medcat/bin/python scripts/smoke_e2e_http.py` | all checks passed |
| Existing CLI (`bin/medai-epi`) | `venv/bin/python scripts/smoke_cli.py` | all checks passed |
| **New** chain + ledger + review queue + review UI | `PYTHONPATH=/tmp/flask_site venv-medcat/bin/python scripts/smoke_chain_http.py` | all checks passed (24 HTTP + 5 CLI) |
| Chain CLI with replayed Med42 output (F-S letter EA0161) | `scripts/extract_chain_cli.py ... --llm-manifests data/run_manifests_fs_test_flat --llm-arm L0` | 17 claims; 4 LLM agreements, 1 disagreement, 1 LLM-only; ran without a GPU |

`/tmp/flask_site` is a directory of symlinks to the Flask packages inside `venv`. It is a
workaround for H9, not a fix.

What the new smoke test shows: the `field_path`, `detectors` and `alternative` fields survive
HTTP → ledger → review queue; an LLM quote that is not in the note is rejected and counted; a
scalar disagreement goes to review with the LLM value preserved; LLM-only claims are never
auto-accepted.

Observed, not yet fixed: the specialist emits claims for fields it did not actually find
(`medication.drug_resistance_status` = `undefined`, `integrated.concordance` = `not_assessed`).
They are rejected as `offsets_unresolved`, so they do no harm to the accepted set, but they
inflate `n_rejected` (2 of 3 rejects in the smoke note). This is the audit finding F1
(valid does not mean populated) showing up on the specialist path; filter placeholder values
before claim creation, then re-measure reject counts.

Update 2026-10-01 (`leo-v0.4`): the placeholder-field problem above is partly addressed for
seizure frequency (empty values dropped before fusion, `drop_empty_frequency`); the other
placeholders (`drug_resistance_status`, `concordance`) are still emitted and rejected. The review
UI and `/extract/chain` need no change for the new `medication.acute_administration` field path:
it is carried through the ledger as an ordinary path (smoke test passed).
