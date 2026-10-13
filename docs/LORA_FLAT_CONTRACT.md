# LoRA on the flat contract (H2) — keep off fusion unless it agrees with E

Measured: H2 **alone** +0.04 F1 vs L1C on F-S (0.74 vs 0.70). **Fused** LEO+H2 reviewed **0.69** — worse than H2 alone. Default stays base L1C (`--h2` opt-in; extra readers off with an adapter).

## Why fusion got worse

The adapter was trained to emit the gold table, not to corroborate EpExtra. On disagreement it fights E. Fusion shows E (D17) and sends the cell to review; the adapter’s extra recall never becomes ACCEPT, and some agrees are wrong in a new way.

Exam-QA LoRA (MedQA) is a different job. Do not treat a bigger MedQA score as phenotyping gain.

## If we train again (not run in this pass)

Positive examples = notes where **E and L1C already agree and the quote entails the cell**, plus reviewer-corrected quotes after IRB. Loop C is **paused**; `leo learn --lora` is refused until a frozen held-out set exists (`docs/ACTIVE_LEARNING_PLAN.md`). Loss = flat-contract JSON (same `PROMPT_TEMPLATE` as H2), greedy, constrained. Goal: the adapter copies E on E-easy cells and only adds recall where E was silent.

Do **not**: train on M2 schema-echo traces; train so the adapter overrides E; fuse H2 as default without a new EVAL.

`--h2` remains optional. Constrained decoding stays on for L1C (`generate_constrained`, `do_sample=False`, `seed=0`). Schema-in-prompt (M2) stays a reported negative result (F3).
