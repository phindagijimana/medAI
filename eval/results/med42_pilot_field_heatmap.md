## Base-Med42 per-field HIT rate on 60-doc pilot (Table 5c candidate)

*Each row: one required field across the strict-scored set. Columns: HIT count / total docs where the field was applicable.*

| Field | M0 HIT | M1 HIT | M2 HIT | note |
|---|---|---|---|---|
| `clinical_seizure.epilepsy_type` | 0/40 | 0/40 | 0/40 | closed enum, high content signal — most likely to hit |
| `clinical_seizure.seizure_frequency.count_max` | 0/20 | 0/20 | 0/20 | numeric — requires exact value match |
| `clinical_seizure.seizure_frequency.count_min` | 0/20 | 0/20 | 0/20 | numeric — requires exact value match |
| `clinical_seizure.seizure_frequency.period` | 0/20 | 0/20 | 0/20 | closed enum day/week/month/year |
| `eeg.background` | 0/20 | 9/20 | 0/20 | EEG applicable to P005/P006 only (n=2 docs per arm) |
