# Specialist on phenotypes whose reference is in the generation plan or the F-S gold (no LLM)

## Synthetic: stopped (prior) drugs, polish patients only (the plan has PRIOR_ASMS only there)

| stratum | patients (with reference) | precision | recall | F1 | stopped drug listed as current |
|---|---|---|---|---|---|
| polish90 (90; the adapter was trained on these) | 90 (65) | 0.54 | 0.885 | 0.671 | 25 |
| polish_val (10, held out from the adapter) | 10 (5) | 0.421 | 0.8 | 0.552 | 2 |

Precision counts a stopped drug the rules list but the plan does not as wrong; the generator may have mentioned such drugs in the notes without putting them in the plan, so precision is a lower bound.

Reason class on drugs found by both (reference inefficacy / intolerance -> rules):
- polish90 (90; the adapter was trained on these): {'intolerance -> unspecified': 8, 'intolerance -> intolerance': 84, 'inefficacy -> unspecified': 7, 'inefficacy -> intolerance': 12, 'inefficacy -> inefficacy': 4, 'intolerance -> inefficacy': 1}
- polish_val (10, held out from the adapter): {'inefficacy -> intolerance': 1, 'intolerance -> intolerance': 7}

Failed drugs in the ILAE sense (reference = stopped for inadequate seizure control; rules = failed bucket or inefficacy status):

| stratum | precision | recall | F1 | tp / fp / fn |
|---|---|---|---|---|
| polish90 (90; the adapter was trained on these) | 0.4 | 0.148 | 0.216 | 4 / 6 / 23 |
| polish_val (10, held out from the adapter) | None | 0.0 | 0.0 | 0 / 0 / 2 |

## Synthetic: etiology specifics (gene, variant, antibody)

| stratum | patients with reference | gene right | variant right | antibody right | any claim | false alarms (patients with none in plan) |
|---|---|---|---|---|---|---|
| synth_v3 eval (20) | 1 | 1/1 | 1/1 | - | 1 | 0 |
| synth_v3 ext (80; not looked at while the v0.4/v0.5 rules were written) | 12 | 7/7 | 7/7 | 5/5 | 12 | 0 |
| polish90 (90; the adapter was trained on these) | 13 | 7/7 | 7/7 | 6/6 | 13 | 0 |
| polish_val (10, held out from the adapter) | 1 | 1/1 | 1/1 | - | 1 | 0 |

The synthetic specifics are few (13 v3 and 14 polish patients); intervals are wide. The polish corpus is one the rules were developed against.

## F-S letters

| letters | rescue (tp/fp/fn) | rescue P / R | coarse EEG result right | EEG confusion | etiology cause present: reference vs rules |
|---|---|---|---|---|---|
| held-out letters EA0161-EA0200 (40) | 1/0/0 | 1.0 / 1.0 | 8/14 | {'Abnormal -> Abnormal': 7, 'Normal -> Normal': 1, 'Abnormal -> none': 5, 'Normal -> none': 1} | {'reference False, rules False': 28, 'reference False, rules True': 7, 'reference True, rules True': 5} |
| all 200 letters | 6/6/3 | 0.5 / 0.667 | 37/67 | {'Abnormal -> none': 18, 'Abnormal -> Abnormal': 34, 'Normal -> Normal': 3, 'Normal -> none': 11, 'Normal -> Abnormal': 1} | {'reference False, rules True': 51, 'reference False, rules False': 121, 'reference True, rules True': 24, 'reference True, rules False': 4} |

Rescue: reference = F-S prescriptions with Frequency As_Required (9 in 200 letters). Coarse EEG: reference = EEG_Results Normal or Abnormal where an EEG was performed; rules = abnormal if interictal epileptiform discharges or a non-normal background were found, normal if they were explicitly absent or the background was normal, otherwise none. This is a proxy: an abnormal EEG can show neither. Etiology cause: presence only.
