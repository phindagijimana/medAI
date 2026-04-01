sample_patient_visits — test dataset for NLP / RAG / validation
================================================================

CONTENTS
  patient_visits.csv   UTF-8 CSV: one row per outpatient or ED-style visit.
  _generate_csv.py     Regenerates patient_visits.csv (python3 _generate_csv.py)

COLUMNS
  patient_id       Synthetic ID (SYN-*), not a real MRN.
  visit_id         Synthetic encounter ID.
  visit_date       ISO date (fictional).
  specialty        Neurology subspecialty label.
  chief_complaint  Short reason for visit.
  clinical_note    Full free-text note including, where relevant:
                   - EEG REPORT sections (technique, findings, impression)
                   - MRI BRAIN (or spine/orbits) sections (technique, findings, impression)
                   - Assessment / Plan

NATURE OF DATA
  Fully synthetic, de-identified vignettes written for software testing.
  Not real patient data. Not sourced from live EHR exports.
  Clinical patterns are aligned with public guideline frameworks cited in
  data/guidelines/neurology_guidelines.json and open literature styles
  (e.g. ILAE seizure concepts, stroke MRI patterns, ICHD-3-style headache text).

USE
  Import as pandas.read_csv(..., encoding="utf-8"). Clinical_note may contain
  newlines inside quoted fields (standard CSV).
