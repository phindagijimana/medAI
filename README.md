# MedAI - Medical Analysis Platform

AI-powered medical analysis with clinical guidelines and expert validation system.

## Overview

MedAI is a medical analysis platform featuring:
- Clinical examples across epilepsy, Parkinson's, stroke, dementia, and other neurological conditions
- Integrated clinical guidelines (ILAE, AAN, AHA/ASA, MDS)
- Expert validation system for continuous improvement
- Flexible deployment (local workstation or HPC cluster)

**Current Focus**: Neurology (expanding to additional specialties in future phases)

## Quick Start

### Local
```bash
git clone https://github.com/phindagijimana/medai.git
cd medai
./medai start
```
Access at http://localhost:8085

### HPC
```bash
git clone https://github.com/phindagijimana/medai.git
cd medai
./medai-hpc install
./medai-hpc run gpu    # or 'run cpu' for CPU-only
./medai-hpc status
```

## CLI Commands

### Local (`./medai`)
```bash
./medai install        # pip install -r requirements.txt
./medai start          # Gunicorn in background (production-style)
./medai start -f       # Flask dev server in foreground
./medai start -p 8090  # Port (also SERVICE_PORT)
./medai status         # Check status
./medai logs           # View logs
./medai stop           # Stop service
./medai restart
```

Use `MEDAI_PIP_USER=0` when using a venv so `pip install` does not pass `--user`.

### HPC (medai-hpc)
```bash
./medai-hpc install             # Setup
./medai-hpc run gpu             # Submit GPU job
./medai-hpc run cpu             # Submit CPU job
./medai-hpc status              # Check status
./medai-hpc logs                # View logs
```

## Requirements

**Minimum**:
- Python 3.8+
- 2GB RAM
- Flask, pandas, numpy (auto-installed)

**For AI Model**:
- PyTorch 2.1+
- 16GB+ GPU VRAM (GPU mode) or CPU fallback
- CUDA 11.7+ (GPU mode)

## Documentation

See `DEPLOYMENT.md` for complete deployment guide, GPU setup, HPC configuration, and troubleshooting.

**Self-hosting (Gunicorn, env vars, Docker):** see [`SELF_HOSTING.md`](SELF_HOSTING.md) and [`.env.example`](.env.example).

## Tech Stack

- Backend: Flask, Python 3
- Database: SQLite
- Optional: PyTorch, ChromaDB

## License

MIT

## Support

GitHub Issues: https://github.com/phindagijimana/medai/issues
