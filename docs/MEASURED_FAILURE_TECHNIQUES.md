# Techniques that hit measured LEO failures (2026-10-07)

Not more ILAE gazetteer strings (v4_ext rematch: headline F1 did not move). Not CoT / 70B / MedQA.

| Technique | Where | Shipped | Default |
|---|---|---|---|
| Status/time: “was stopped”, PLAN→hypothetical, later stop wins, “that drug” | E meds | yes | on (same family as LPD negation) |
| Quote–value entailment | fusion | `--quote-entail` | **off** (scored 10.49: P up, R down, 16 correct demoted; do not flip) |
| Per-field routing from adjudication | fusion | `--disagree-llm policy:FILE` after `--emit-policy` | D17 rules everywhere |
| Med role / section | E | PLAN/PMH flags + existing i2b2/ctakes sidecar | on for flags; ctakes still opt-in |
| Section detector | E | already Phase 4; PLAN = hypothetical | on |
| LoRA flat contract | L | H2 optional `--h2` | **off fusion** |
| Constrained decoding | L | L1C `generate_constrained` | **on** |
| Span/BIO NER | E or sidecar | `--ext-detector ner-onset` etc. **raise** until trained | blocked |
| Coref + temporal | E meds | `services/coref_temporal.py` | on, narrow |
| Patient roll-up | fusion | latest note, not union (`leo rollup`) | opt-in CLI |
| Visit glance column | display | `visit_summary` from this note’s cells, under 50 words (`[?]` = review) | on; not scored |
| Active learning | labels → routing/thresholds | `bin/leo learn` (A/B); Loop C paused | not wired to extract |

D17, research extract, and greedy seed-0 are unchanged unless you pass the new flags.

Living register of holes and next steps: `docs/WEAKNESSES.md`.
