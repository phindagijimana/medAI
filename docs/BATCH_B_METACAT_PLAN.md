# Batch B — MetaCAT Training on F-S 160 Train

**Status:** deferred to fresh session. Requires ~1-2 hours GPU + gold-format conversion.

## Rationale

ExECT-V2 has a trained MetaCAT ML disambiguator (fine-tuned on SAIL data). Our pipeline uses dict-mode with `primary_name_only_linker`, which handles the many-to-one ambiguity issue without training. Projected MetaCAT lift: +2-3% F1.

**Risk:** MetaCAT trained on F-S UK letters may overfit UK style and regress synth-v1/MTSamples cross-domain performance. Mitigate via regression check on synth-v1 (must stay ≥ 0.78).

## Prerequisites

- Trained MedCAT vocab (`Vocab` object with word vectors)
- Annotated span-level data (not phenotype-level) — our F-S silver-label JSONs are phenotype-shaped, not span-shaped

## Gold-format conversion required

MedCAT 2.x MetaCAT training expects one of:
1. **MedCATtrainer project export** (JSON with per-span annotations)
2. **BRAT-style .ann files** (T1 T2 ... A1 A2 ...)
3. **Custom Doc JSON** with `entities[]` at char-span level

Our current gold (`data/fonferko_shadrach_2024/silver_labels_v0_2_1/EA*.json`) has:
- Field values at phenotype level (e.g., `clinical_seizure.predominant_seizure_type.value`)
- Evidence text quotes (but no char offsets)

**Conversion approach:**
1. For each gold field with an evidence quote, `str.find()` the quote in the note text to derive char span
2. Emit MedCAT-format entity with the enum's CUI + attribute annotations
3. ~4-6 hours engineering; ~90% coverage (some evidence quotes are paraphrased)

## Training command sketch (MedCAT 2.9)

```python
from medcat.cat import CAT
from medcat.model_creation.metacat_creation import MetaCATCreation

cat = CAT.load("data/medcat_cdb_epilepsy/cdb.zip")
mc = MetaCATCreation(cat=cat, category_name="Negation")  # or Temporality, etc.
mc.train(
    training_docs_path="data/metacat_training/fs_160_train.json",
    device="cuda",  # or "cpu" (~8 hours)
    epochs=10,
    lr=1e-4,
)
```

## Evaluation gate

After training:
1. Rebuild CDB with MetaCAT attached
2. Rescore F-S 40 held-out — expect +2-3% F1
3. Rescore synth-v1 held-out — must stay ≥ 0.78 (no regression)
4. If synth-v1 regresses > 0.02, roll back and document as "MetaCAT overfits UK style"

## Alternative: skip MetaCAT for now

Our current F-S 40 F1 = 0.8064 is within the 0.72-0.85 target range. MetaCAT lift is +2-3% which brings us to ~0.83, but at cost of engineering (~1 day) + cross-domain risk.

**Recommendation:** defer MetaCAT until:
- F-S 40 F1 target moves above 0.85 (currently comfortable at 0.81), OR
- MTSamples F1 becomes the bottleneck (currently 0.40, would benefit more from US-idiom rules than MetaCAT)

## When to revisit

- After LoRA v4 fine-tune with synth-v2 lands (if arm M4 catches up to arm B1', comparison paper needs a stronger B1')
- If reviewers ask for it during paper submission
- If a US clinical partner needs deployment-grade accuracy

Estimated total effort when revisited: 1 day gold conversion + 1 day training + 0.5 day validation.
