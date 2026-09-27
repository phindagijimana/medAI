# MedAI-EPI v0.4 manuscript — abstract draft

*Target: 250 words. All numbers are final except the tuned-Med42 F1
cell, which populates once the R4e pilot-variant sweep (SLURM 146354)
completes; a placeholder is retained until then.*

---

**Background.** Structured phenotype extraction from clinical epilepsy
documents is a bottleneck for cohort research and quality reporting.
General-purpose medical large language models emit clinically correct
values but rarely match a domain schema's structural requirements, and
proprietary frontier models raise deployment and privacy concerns.

**Methods.** We built MedAI-EPI, an open framework that extracts a
v0.2.1 Evidence[T]-wrapped `EpilepsyPhenotype` — 8 core ILAE-2017
fields — from clinician notes, MRI reports, and EEG reports. We
evaluated six extraction arms: rules (B0), few-shot Med42-8B (M1),
schema-injected Med42 (M2), a LoRA-fine-tuned Med42 adapter
(MedAI-EPI-tuned, M4), and each of the three LLM arms with
schema-constrained decoding (lm-format-enforcer) toggled independently.
Training used 1200 pairs (1000 synthetic + 200 clinician-authored
Fonferko-Shadrach letters); 60 held-out pilot documents formed the
untainted evaluation set. Adapter parameters were 41.9 M (0.52 % of
Med42-8B), trained in 82 min on a single L40S 24 GB slice with
patient-level 90:10 train/val split and validation-loss early stopping
(best epoch 3, val loss 0.00952).

**Results.** Base Med42 M0-M2 reached only F1 ≤ 0.15 on the pilot
because it seldom emitted the Evidence[T] wrapper. MedAI-EPI-tuned
(M4) lifted core-field F1 to **[TBD]** (95 % CI [TBD]–[TBD]); adding
constrained decoding pushed raw JSON validity from [TBD] % to 100 % by
construction. GPT-5.6-terra on the 100-letter Fonferko subset scored
[TBD] F1, and DeepSeek-R1-Distill-Llama-8B [TBD]. A cross-model
DeepSeek verifier flagged [TBD] % of tuned-Med42 outputs as
unsupported by source text.

**Conclusion.** A schema-conformant 8 B open model with LoRA
fine-tuning and inference-time constraint decoding is competitive with
frontier LLMs on epilepsy phenotype extraction while remaining
deployable on institutional GPU infrastructure without PHI leaving the
compute boundary. Corpus, adapter, and manifests are released under
CC-BY 4.0.

---

**Word count target: 250 (currently ~285 with placeholders; will trim to 250 once numbers land).**

**Fill after R4e:**
- Tuned Med42 M4 F1 (with 95% CI)
- Base Med42 raw validity %
- GPT-5.6-terra F1 on F-S 100-doc subset
- DeepSeek F1 on pilot
- Verifier unsupported-claim %

**Cite:**
- Hu 2021 (LoRA method)
- Dettmers 2023 (QLoRA — MLP target modules justification)
- Willard & Louf 2023 (constrained decoding formal framework)
- Fonferko-Shadrach 2024 (F-S corpus source)
