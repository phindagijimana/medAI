# Documentation

Local documentation files (not tracked in GitHub, see root for public docs).

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

- **`LEO_USER_GUIDE.md`**: how to run LEO (`bin/leo`, Slurm GPU/CPU, web app), input and output formats, phenotype panels, questions, long notes, data protection
- **`LEO_ROUTING_RULES.md`**: how LEO fuses the specialist (EpExtra) and the LLM and decides ACCEPT, REVIEW or REJECT
  - Fusion table, verification order, reason codes, the leo-v0.4 and v0.5 rules (acute, rescue, frequency) and their switches
- **`EVAL_PROTOCOL_LEO.md`**: frozen evaluation protocol, deviations log (D1 to D11), append-only results log
- **`SCOPE_DECISIONS.md`**: deferred scope items (ILAE 2025, NINDS CDE, ICD-10-CM, EpSO, ORDO, definition of current ASM)
- **`CHAIN_OF_THREE_ALIGNMENT.md`**: mapping of the Chain-of-Three design to the code, with change log

## Public Documentation

Main documentation (tracked in GitHub):
- `../README.md`: Project overview and quick start
- `../DEPLOYMENT.md`: Complete deployment guide

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
