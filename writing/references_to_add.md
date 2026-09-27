# References to add / verify for MedAI-EPI manuscript v0.4

Companion to `writing/MedAI_EPI_Manuscript_v0.4_additions.md` (R7 draft).
This file is a machine-readable checklist: (a) references to add for the
v0.4 fine-tuning + constrained-decoding additions, (b) references in the
existing v0.2 manuscript flagged for DOI / typo verification at final
proof. Update the `status` column as each item is verified.

---

## (a) New references introduced by v0.4

Cited in the body via `^{ShortKey}` anchors. Assemble into the final
numbered reference list when merging v0.4 into v0.2.

| Short key | Citation | Cited in §                    | Verified? |
|---|---|---|---|
| Hu2021        | Hu EJ, Shen Y, Wallis P, Allen-Zhu Z, Li Y, Wang S, Wang L, Chen W. *LoRA: Low-Rank Adaptation of Large Language Models.* arXiv:2106.09685. 2021. https://arxiv.org/abs/2106.09685 | Fine-tuning (LoRA reference) | [ ] |
| Dettmers2023  | Dettmers T, Pagnoni A, Holtzman A, Zettlemoyer L. *QLoRA: Efficient Finetuning of Quantized LLMs.* arXiv:2305.14314. 2023. https://arxiv.org/abs/2305.14314 | Fine-tuning (target-module choice + loss-masking convention) | [ ] |
| Willard2023   | Willard BT, Louf R. *Efficient Guided Generation for Large Language Models.* arXiv:2307.09702. 2023. https://arxiv.org/abs/2307.09702 | Schema-constrained decoding (parser-mechanics paragraph) | [ ] |

---

## (b) v0.2 citations flagged for DOI / typo verification

Cross-check every entry in `MedAI_EPI_Manuscript_v0.2.md` §References
against Google Scholar / PubMed / DOI resolvers before submission. The
items below have specific typo / metadata concerns that need attention.

| v0.2 ref # | Citation (abbreviated)                                                       | What to verify                                                      | Verified? |
|---:|---|---|---|
|  6 | Abeysinghe et al. 2025, *NPJ Digit Med.* 8:208                               | Volume/issue/pages; spelling of "Lhatoo"; correct journal short name | [ ] |
|  7 | Adelson PD et al. 2026, *Epilepsia* doi:10.1002/epi.70341                    | DOI resolves; title text ("Engel and ILAE scoring") matches published record | [ ] |
| 13 | Ndagijimana P et al. 2026, *Brain Communications* 8(4):fcag320               | Article ID "fcag320"; sanity-check against accepted-manuscript record | [ ] |
| 14 | Christophe C et al. 2024, Med42-v2, arXiv:2408.06142                         | arXiv ID; title casing ("A Suite of Clinical LLMs")                 | [ ] |
| 15 | Fonferko-Shadrach B et al. 2024, *J Biomed Semantics* 15:17                  | "Strafford" spelling; page numbers                                  | [ ] |
| 17 | Li J et al. 2021, synthetic clinical notes for NER, *JAMIA* 28(10):2193–2201 | v0.2 already flags: full author list + page range against DOI       | [ ] |
| 18 | Goldenholz DM et al. 2025, *Epilepsy Res.*                                   | v0.2 already flags: volume, pages, DOI against final PubMed record  | [ ] |
| 19 | Alsentzer E et al. 2019, Clinical BERT embeddings                            | Workshop proceedings pages 72–78                                    | [ ] |

Note: refs 1–5, 8–12, 16 in v0.2 were not flagged by inspection, but
should still be spot-checked during copy-edit. Ref 16 is an internal
protocol pointer (`docs/PROTOCOL_SHAPE_A.md` + `paper_doc/`) — leave as
internal or replace with an archival citation when the protocol is
deposited.

---

## (c) Not-yet-cited but likely needed for v0.4

Candidate references identified while drafting v0.4 that are NOT yet
inserted into the body — decide at review whether to fold them in:

- Han et al. 2021 (T5 / instruction-tuning loss masking convention).
  The v0.4 §Fine-tuning paragraph attributes the loss-masking convention
  to "Han et al. 2021 and formalized in QLoRA (Dettmers 2023)". If
  reviewers ask for the primary reference for masked-loss instruction
  tuning, the closest candidate is:
  - Han X et al. *Pre-Trained Models: Past, Present and Future.*
    AI Open. 2021;2:225-250. https://arxiv.org/abs/2106.07139
  Alternatively, cite Wei et al. 2022 FLAN
  (https://arxiv.org/abs/2109.01652) as the instruction-tuning progenitor
  that established prompt-token masking in the T5-XXL setting.
- OpenAI Structured Outputs (2024) as a comparator to lm-format-enforcer
  for the §Schema-constrained decoding paragraph, if reviewers ask why
  we chose LMFE over the OpenAI SDK feature.
- vLLM guided-decoding docs (2024) — engineering reference for readers
  reproducing the constrained arm on their own infra.
