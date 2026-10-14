# Quick start

**Research use only.** Synthetic notes unless you have IRB and approved compute.

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
bin/leo rollup notes_leo.csv --patient-col patient_id
bin/leo asm-view notes_leo.csv --view maintenance
```

GPU extract needs Med42-8B weights, the epilepsy CDB, and a UMLS key in `.env` (never committed). CPU-only is **not** a research extract.

Where to put files and how to set `--gres`: [Installation](LEO_HOSTING.md). Full command list: [Usage](LEO_USER_GUIDE.md).
