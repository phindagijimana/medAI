# LEO L1C efficiency (F-S held-out manifests; no re-run)

n=40  model=`m42-health/Llama3-Med42-8B`  arm=`L1C`  gpu=`NVIDIA L40S-24Q`

| | mean | median | min | max | sum |
|---|---:|---:|---:|---:|---:|
| duration (s) | 10.72 | 10.67 | 8.72 | 14.17 | 428.6 |
| completion tokens | 183.0 | 181.0 | — | 266 | — |
| note characters | 1143 | 1112 | — | 2368 | — |

These are **model generate() times** from the stored manifests, not end-to-end LEO (specialist + fusion + extra readers). Specialist-only CPU on the same 40 letters is a separate pass.
