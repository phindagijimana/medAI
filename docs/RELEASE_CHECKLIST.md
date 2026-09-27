# MedAI-EPI v1.0 — release checklist

Everything below is a step the **user** (repo owner) must perform
manually — either because it requires an account/credential Claude
cannot use, or because it is a one-way action that should not be
automated. Steps are ordered by dependency.

---

## 1. Upload synth-v1 corpus to Zenodo → get DOI

1. Build the archive: `tar czf synth_v1.tar.gz data/episynth_corpus/v1/`.
2. Log in at https://zenodo.org (institutional or GitHub-linked
   account).
3. Click **New Upload**.
4. Attach `synth_v1.tar.gz` (and optionally a compressed `patients/`
   + `documents/` split for browsable preview).
5. Copy the description from `docs/zenodo_readme.md` (§Description,
   §Contents, §Provenance and reproducibility, §Intended use,
   §Ethics, §Citation) into the Zenodo record.
6. Under **Related identifiers**, add:
   - Fonferko-Shadrach records: 8381080, 8356494, 8382589, 12520180
     (Relation: *is derived from* — even though synth-v1 is not
     derived from them, they are cited).
   - Manuscript preprint DOI (once available): *is supplement to*.
7. License: **CC-BY 4.0**.
8. Version: **v1** (Zenodo will assign a concept DOI + version DOI).
9. Publish.
10. Record the version DOI (looks like `10.5281/zenodo.NNNNNNNN`).

## 2. Upload LoRA adapter to Hugging Face → get repo URL

1. `huggingface-cli login` in a shell that has your write token.
2. Create the repo (choose an org or personal namespace):
   ```
   huggingface-cli repo create medai-epi-tuned --type model
   ```
3. Clone the empty repo, copy the adapter files:
   ```
   cd /tmp && git clone https://huggingface.co/<user>/medai-epi-tuned
   cd medai-epi-tuned
   cp -r $REPO/checkpoints/llama3-med42-8b_lora_epi/adapter_config.json .
   cp -r $REPO/checkpoints/llama3-med42-8b_lora_epi/adapter_model.safetensors .
   cp $REPO/docs/huggingface_model_card.md README.md
   ```
4. Edit `README.md` (the model card) to replace every remaining
   `[TBD]` with concrete values (rank, alpha are already 16 / 32;
   fill validation loss, best epoch, wall-clock, and paper DOI
   once available).
5. `git add . && git commit -m "Initial release v1.0" && git push`.
6. The public URL is `https://huggingface.co/<user>/medai-epi-tuned`.

## 3. Fill DOIs / URLs back into repo docs

Search-and-replace `[TBD]` in these files with the values obtained
in steps 1 and 2:

- `RELEASE_NOTES.md` — Zenodo DOI (software record + corpus), HF URL,
  manuscript DOI, release date.
- `docs/zenodo_readme.md` — record DOI, release date.
- `docs/huggingface_model_card.md` — HF repo URL, base-license line,
  paper DOI, wall-clock, best epoch, best val loss.
- `writing/MedAI_EPI_Manuscript_v0.4.md` — §Data availability
  Zenodo DOI + HF URL, §Fine-tuning wall-clock and best-epoch cells.

Commit these edits: `git add -u && git commit -m "R8: fill Zenodo /
HF URLs into release docs"`.

## 4. Tag v1.0

```
git tag -a v1.0 -m "MedAI-EPI v1.0 — first citable release.
See RELEASE_NOTES.md for details.
Zenodo DOI: <fill in>
HuggingFace: <fill in>"
```

## 5. Push the tag

```
git push origin v1.0
```

If the remote is Zenodo-linked via the GitHub-Zenodo integration, a
software-record DOI is auto-created; copy it back into
`RELEASE_NOTES.md` "Zenodo DOI (software record)" (this can be a
separate follow-up commit — the tag itself is immutable, but the DOI
field in RELEASE_NOTES.md just tracks it).

## 6. Draft arXiv / medRxiv submission

1. Open `writing/MedAI_EPI_Manuscript_v0.4.md`.
2. Verify all remaining `[TBD]` markers are filled (grep for it —
   the R7 checklist and this document leave only the release URLs).
3. Convert to LaTeX / Word per the target venue's template.
4. Upload to medRxiv (biomedical preprint) or arXiv q-bio.QM
   (biomedical NLP methods).
5. Copy the preprint DOI back into `RELEASE_NOTES.md` §v1.0 and
   `docs/zenodo_readme.md` §Citation. Commit.

---

## Do-not-do list

- **Do not** amend the v1.0 tag after pushing — create v1.0.1 for
  post-release fixes. Zenodo's software record integration relies on
  tag immutability.
- **Do not** publish the LoRA adapter without the Med42-8B upstream
  license attribution — see the HF model card's §License section.
- **Do not** publish the raw OpenAI request/response envelopes from
  `data/episynth_corpus/v1/documents/*/request.json` if any include
  system-prompt secrets. They should not (the corpus generator uses a
  fixed public prompt template), but grep first:
  ```
  grep -RE 'sk-|OPENAI_API_KEY' data/episynth_corpus/v1/
  ```
- **Do not** push to `main` between the v1.0 tag and the Zenodo /
  HF-URL fill-in commits — those commits should be linear on top of
  the tag so users cloning `main` see the finalized release notes.

---

## Rollback

If v1.0 needs to be withdrawn (e.g. a critical bug in the adapter
weights):

1. `huggingface-cli` — mark the model repo private or add a "gated"
   flag, and post a `README.md` notice.
2. Zenodo — you cannot delete a published record; issue a new version
   with a "WITHDRAWN" notice in the description.
3. `git tag -d v1.0` locally (this does NOT delete the remote tag);
   push a **new** annotated tag `v1.0.1` or `v1.1` with the fix.
