# Courtesy Email Draft — Fonferko-Shadrach ExECT-V2 Group

**Status.** Draft. Intended to be reviewed by the MedAI-EPI PI and sent from
a signed institutional address; not to be automated.

**Purpose.** Announce our US-side reimplementation of ExECT-V2 logic in
Python (MedCAT + medspaCy) as a research comparator in the MedAI-EPI paper,
ask for explicit open-source relicensing to enable proper attribution, and
open the door to cross-corpus collaboration.

**Suggested recipients.**

- Dr Beata Fonferko-Shadrach (Swansea University; corresponding author of
  the 2019 BMC Med Res Methodol + 2024 J Biomed Semantics papers).
- Dr Arron Lacey (Swansea University; co-author + maintainer of the
  \`arronlacey/ExECT\` v1 fork).
- cc Dr Owen Pickrell (Swansea University; PI on both papers).

Optionally cc your own PI + program manager at URMC.

---

## Subject line (pick one)

- **Preferred:** `US reimplementation of ExECT-V2 for research comparison — MedAI-EPI (University of Rochester)`
- Alternative: `Enquiry re: ExECT-V2 licensing + potential US cross-corpus collaboration`

---

## Body

> Dear Dr Fonferko-Shadrach, Dr Lacey, and Dr Pickrell,
>
> I hope this note finds you well. My colleagues and I at the University of
> Rochester Medical Center are building a research framework called
> **MedAI-EPI** for structured epilepsy phenotype extraction from clinical
> notes. The paper compares several extraction approaches — an ontology-aware
> rule-based baseline, a fine-tuned Med42-8B (LoRA) system, GPT-family and
> DeepSeek comparators, and a specialized rule-based comparator informed by
> your ExECT-V2 pipeline — across six US and UK corpora.
>
> We have studied both the `swneurosci/ExECT-V2` and `arronlacey/ExECT`
> repositories in detail, along with your 2019 BMC Medical Research
> Methodology paper and the 2024 J Biomed Semantics annotation-guidelines
> paper. We are impressed by the depth of the rule set and the quality of
> the ILAE→UMLS/SNOMED-CT mapping in `Other/ILAE proposed map to UMLS and
> SNOMEDCT.xlsx`. Our plan is to *reimplement the pipeline logic
> independently* in Python (MedCAT + medspaCy + hand-authored rules), citing
> your work prominently in the manuscript, rather than fork the GATE
> distribution. This choice is partly technical — our downstream stack is
> Python and we need a US-adapted variant — and partly a licensing
> caution, since neither repository currently carries an explicit LICENSE
> file. We are treating ExECT-V2 as reference material only; no verbatim
> JAPE or Groovy code will land in our tree, and we will not redistribute
> your custom-UMLS dictionaries.
>
> Two questions:
>
> 1. **Licensing.** Would you be willing to attach an explicit permissive
>    open-source license (e.g. Apache 2.0 or CC-BY-4.0) to
>    `swneurosci/ExECT-V2`? An explicit license would let us cite specific
>    files and rule modules by line reference in the manuscript's supplementary
>    materials, which is a much stronger form of attribution than the
>    "reimplemented logic, cited-only" pattern we are currently obliged to
>    adopt. It would also let follow-on groups build on ExECT-V2 without the
>    ambiguity we have had to navigate.
>
> 2. **Collaboration.** If a cross-corpus validation of ExECT-V2 against US
>    clinical text (MTSamples neurology, MIMIC-IV epilepsy discharge
>    summaries, and our synthetic US corpus) would interest you, we would
>    welcome the conversation. We can share our schema (v0.2.1, 24 enums, 7
>    modules), our synthetic and human-annotated evaluation corpora, and
>    early scoring results as soon as we have them.
>
> We plan to include acknowledgement of ExECT-V2 in the manuscript
> regardless of the outcome of these questions, along with a dedicated
> supplementary table mapping the ~220 Python rules in our arm B1' back to
> the ExECT-V2 files they are informed by.
>
> Happy to share our current writeup and code plan on request, and to speak
> by video call at your convenience. Thank you very much for your work on
> ExECT-V2 — it has been the single most useful open-source reference for
> this project.
>
> With best wishes,
>
> —
>
> **MedAI-EPI team**
> University of Rochester Medical Center
> Rochester, NY, USA
> [Signature block — PI name, appointment, email, ORCID]

---

## Sender's checklist before sending

- [ ] Confirm current corresponding-author email addresses on the 2024 J
      Biomed Semantics paper (may differ from the 2019 paper).
- [ ] Attach a one-page PDF summary of MedAI-EPI (schema screenshot, arm
      list, corpus list) so the recipient can react in five minutes.
- [ ] Have PI + program manager approve the licensing ask (para 3, item 1)
      before sending. Some institutions require IP-office sign-off for any
      wording that touches licensing.
- [ ] Send from a `@urmc.rochester.edu` address, not from a personal
      account.
- [ ] BCC the MedAI-EPI shared mailbox for archival.

## Follow-up policy

- No response in **2 weeks** → send a one-paragraph nudge referencing the
  original message.
- No response in **6 weeks** → proceed with the "reimplement logic, cite
  only" attribution model unchanged and note in the manuscript that we
  reached out. We will still include full attribution.
- Positive response with licensing → update `docs/MedCAT.md` §8, update
  `writing/MedAI_EPI_Manuscript_v0.5_additions.md` attribution paragraph,
  and thank them in Acknowledgements.
