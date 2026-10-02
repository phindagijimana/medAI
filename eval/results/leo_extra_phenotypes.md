# Specialist on the extra phenotypes (synthetic, 30 patients, notes joined, no LLM)

| Phenotype | Reference present | Rules gave a value | Correct | Accuracy (all) | Accuracy (when answered) |
|---|---|---|---|---|---|
| etiology_category | 30 | 30 | 28 | 0.933 | 0.933 |
| drug_resistance | 30 | 30 | 29 | 0.967 | 0.967 |
| mri_normal | 17 | 16 | 16 | 0.941 | 1.0 |
| hippocampal_sclerosis | 17 | 10 | 10 | 0.588 | 1.0 |
| focal_cortical_dysplasia | 17 | 7 | 7 | 0.412 | 1.0 |

A yes/no finding the note never mentions gets no value from the rules (absence is not inferred), while the reference says False; those count against 'all' and not against 'when answered'. Hedged findings are not counted as asserted.

MRI findings (list, micro): precision 0.517, recall 0.882, F1 0.652
Surgery: rules report a procedure for 0 of 30 patients whose reference lists none.

Not scoreable (the reference has no entry): EEG study type, background, ictal onset; seizure semiology; focal motor / non-motor onset; failed, prior and rescue drugs; surgery history (reference lists none); etiology details.
