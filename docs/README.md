# Documentation

Operator and protocol docs. These **are** tracked (`!docs/*.md`). Manuscript drafts in `writing/` and `paper_doc/` stay local (gitignored). Secrets and note-text outputs stay out of git (`.gitignore`).

## Files

- **`QUICK_START.md`**: Quick reference guide
  - Local and HPC deployment commands
  - Resource mode comparison
  - Common troubleshooting

- **`RESOURCE_MODES.md`**: Detailed resource guide
  - CPU vs GPU modes
  - Performance benchmarks
  - Resource allocation guidelines
  - Advanced configuration

- **`HPC_CLI_GUIDE.md`**: HPC deployment guide
  - SLURM job management
  - Module loading
  - Port forwarding
  - Troubleshooting

- **`LEO_USER_GUIDE.md`**: operator guide (commands, Validator, learn, PHI)
- **`IMPLEMENTATION.md`**: A–Z walkthrough, decisions, contributions, weaknesses
- **`WEAKNESSES.md`**: each hole, what accounts for it today, what to improve next
- **`LEO_ROUTING_RULES.md`**: how LEO fuses the specialist (EpExtra) and the LLM and decides ACCEPT, REVIEW or REJECT
  - Fusion table, verification order, reason codes, the leo-v0.4 and v0.5 rules (acute, rescue, frequency) and their switches; opt-in sidecars (`sidecar_only`, D18–D20)
- **`EVAL_PROTOCOL_LEO.md`**: frozen evaluation protocol, deviations log (D1–D24), append-only results log (through 10.39)
- **`FIELD_SPECIALIST_DETECTORS.md`**: extra literature detectors as fusion sidecars (not E gazetteers); shipped `--ext-detector` names and §9 remaining-hole literature map
- **`ROLE_PLACEMENTS.md`**: RAG for ask_/audit, O export codes, ConText ablation inside E; 70B/CoT/SC not shipped
- **`MEASURED_FAILURE_TECHNIQUES.md`**: status/time, quote entailment, routing policy, LoRA-off-fusion, BIO NER blocked
- **`ACTIVE_LEARNING_PLAN.md`**: `leo learn` Loop A/B from validator files; extract unchanged; Loop C paused
- **`LORA_FLAT_CONTRACT.md`**: why fused H2 lost and how a future adapter must agree with E
- **`E_EXTERNAL_BASELINES.md`**: how to score cTAKES/CLAMP/i2b2 *against E* (B-arm; still unscored)
- **`SCOPE_DECISIONS.md`**: deferred scope items (ILAE 2025, NINDS CDE, ICD-10-CM, EpSO, ORDO, definition of current ASM)
- **`CHAIN_OF_THREE_ALIGNMENT.md`**: mapping of the Chain-of-Three design to the code, with change log

## Public documentation

Operator pages on this site / Read the Docs (MkDocs; `docs_dir` is `docs_site/`, symlinks into `docs/`):

- `index.md` — landing
- `LEO_USER_GUIDE.md`, `LEO_HOSTING.md`, `INTERPRETING_RESULTS.md`
- `LEO_ROUTING_RULES.md`, `IMPLEMENTATION.md`, `WEAKNESSES.md`, `ACTIVE_LEARNING_PLAN.md`

Not on the HTML site: `EVAL_PROTOCOL_LEO.md`, paper drafts (`writing/`, `paper_doc/`), hold-out leak tables. Import `phindagijimana/medAI` at readthedocs.org after this config is on `main`.

## Usage

These files are for local reference. They contain detailed information that complements the main documentation.

### Quick Reference
```bash
# View quick start
cat docs/QUICK_START.md

# View resource modes
cat docs/RESOURCE_MODES.md

# View HPC guide
cat docs/HPC_CLI_GUIDE.md
```

### Search Documentation
```bash
# Find deployment info
grep -r "deployment" docs/

# Find GPU info
grep -r "GPU" docs/
```

## Organization

- **Quick guides**: For fast reference during deployment
- **Detailed guides**: For in-depth understanding
- **Troubleshooting**: Common issues and solutions

## Note

These files are in `.gitignore` as they're intended for local use. The main `README.md` and `DEPLOYMENT.md` in the root directory are the canonical public documentation.
