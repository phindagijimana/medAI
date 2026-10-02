# Specialist on the extra phenotypes (synthetic, 80 patients, notes joined, no LLM)

| Phenotype | Reference present | Rules gave a value | Correct | Accuracy (all) | Accuracy (when answered) |
|---|---|---|---|---|---|
| etiology_category | 80 | 80 | 77 | 0.963 | 0.963 |
| drug_resistance | 80 | 80 | 76 | 0.95 | 0.95 |
| mri_normal | 30 | 29 | 29 | 0.967 | 1.0 |
| hippocampal_sclerosis | 30 | 19 | 18 | 0.6 | 0.947 |
| focal_cortical_dysplasia | 30 | 14 | 11 | 0.367 | 0.786 |

A yes/no finding the note never mentions gets no value from the rules (absence is not inferred), while the reference says False; those count against 'all' and not against 'when answered'. Hedged findings are not counted as asserted.

MRI findings (list, micro): precision 0.5, recall 0.933, F1 0.651
Surgery: rules report a procedure for 5 of 80 patients whose reference lists none.

Not scoreable (the reference has no entry): EEG study type, background, ictal onset; seizure semiology; focal motor / non-motor onset; failed, prior and rescue drugs; surgery history (reference lists none); etiology details.
