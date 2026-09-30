# synth-v3 Template Prompts

Twelve US epilepsy note-type templates for the synth-v3 pipeline. Each template routes a `semantic_plan` (patient phenotype) + `encounter_metadata` (visit type, provider persona, timing) through a template-specific GPT prompt.

## Templates

| ID | File | Note type | Anchor |
|---|---|---|---|
| A | `template_A_new_patient_consult.txt` | Neurology/neurosurgery new patient consult letter | Real deidentified exemplar (references/real_us_note_templates/) |
| B | `template_B_telephone_fuv.txt` | Neurology telephone/video follow-up | Real deidentified exemplar |
| C | `template_C_in_person_fuv.txt` | In-person routine follow-up | Structural skeleton (hybrid of A + B) |
| D | `template_D_emu_admission.txt` | EMU admission summary | Skeleton (standard EMU report format) |
| E | `template_E_ed_note.txt` | ED note (seizure workup) | Skeleton (standard US ED note format) |
| F | `template_F_prc_summary.txt` | Patient Review Conference summary | Skeleton (multi-disciplinary review) |
| G | `template_G_mri_report.txt` | MRI brain report (epilepsy protocol) | Skeleton (radiology report format) |
| H | `template_H_eeg_report.txt` | EEG report (routine or long-term) | Skeleton (neurophysiology format) |
| I | `template_I_neuropsych.txt` | Neuropsychology evaluation | Skeleton (cognitive testing format) |
| J | `template_J_discharge_summary.txt` | Post-operative discharge summary | Skeleton |
| K | `template_K_triage_call.txt` | Nurse triage / phone call | Skeleton (brief encounter) |
| L | `template_L_inpatient_progress.txt` | Inpatient daily progress note | Skeleton (daily EMU/inpatient) |

## Prompt structure

Every template follows the same 6-section prompt architecture:

1. **ROLE** — one line establishing GPT as a US clinician
2. **CONTEXT** — encounter type, care setting, provider persona
3. **SEMANTIC PLAN** — patient phenotype (injected from sampler)
4. **STRUCTURAL EXEMPLAR** — reference note structure (for A/B: real deidentified note; for others: format skeleton)
5. **STYLE + REALISM DIRECTIVES** — copy-forward, EMR placeholders, physician shorthand
6. **OUTPUT INSTRUCTIONS** — deidentification requirements, length target

## Realism techniques applied per template

- **Copy-forward artifacts** (for follow-up templates B, C, K, L): "Include prior PMH block verbatim"
- **Template placeholders** (all): "No X on file", "NKDA", "Twelve systems reviewed, all others negative"
- **Physician shorthand** (all): s/p, r/o, hx of, BID, EMU, LTM, MTS, IED, etc.
- **Section header conventions** (varies): Title Case for A; ALL CAPS: for B; mixed for others
- **Time-based billing** (B, C, K): "I have personally spent X minutes..."
- **Telemedicine consent** (B): "Consent was previously obtained..."
- **Deliberate imperfection** (some templates): sentence fragments in exam, occasional typos ≤1/1000 words
- **Longitudinal reference** (C, K, L, J): prior visit narrative + interval history
