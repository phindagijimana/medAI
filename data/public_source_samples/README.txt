public_source_samples — neurology-only structured test data (MIMIC-IV Demo)
============================================================================

We keep ONLY neurology-filtered tables derived from the official PhysioNet
MIMIC-IV Clinical Database Demo v2.2. Full multi-specialty hosp exports are
NOT stored in this repository.

Location: mimic_iv_demo_2.2/

  neurology_diagnoses.csv   — ICD rows matching neurology filter (see script)
  neurology_admissions.csv  — admissions with ≥1 neurology-coded diagnosis
  neurology_patients.csv    — patients for those admissions
  neurology_hadm_ids.txt    — admission IDs
  build_neurology_subset.py — Regenerates the four files (downloads demo from PhysioNet)

Source (same data the script downloads):
  https://physionet.org/content/mimiciv-demo/2.2/

Neurology filter (ICD-based, for software testing):
  ICD-10-CM: G* ; I60–I69 ; R56
  ICD-9-CM: categories 320–389

These are NOT free-text clinical notes. The public demo does not include note
text. For narrative EEG/MRI-style test notes see:
  data/sample_patient_visits/patient_visits.csv

Citation:
  Johnson, A.E.W., et al. MIMIC-IV. Scientific Data (2023). Demo subset on PhysioNet.

Follow PhysioNet license terms when publishing derivatives.
