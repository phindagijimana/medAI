# learning_dkt-connectome — teaching-document template

**Purpose.** This file is a template for a learning document that will accompany work on a DKT-connectome project when it is undertaken with Claude, following the same pattern as `writing/learning_medai.md`.

**Status.** No DKT-connectome tasks have been performed in the current session. The scaffolding below is ready to be filled with project-specific content once that work begins.

---

## How to use this template

When beginning a Claude-driven DKT-connectome task session, extend the sections below with the actual work performed. The template mirrors `learning_medai.md` so the two documents read consistently.

Sections to fill (recommended order):

1. **Project context and framing decisions** — What problem is being solved? Who is the audience (research group, target journal, downstream users)? What framing rules apply (e.g., "not clinical decision support", cohort definition scope)?

2. **Domain theory** — Concepts a reader must know before reading the engineering. For DKT-connectome, candidates:
   - Diffusion imaging + tractography basics
   - Desikan–Killiany–Tourville (DKT) atlas and its 62–68 cortical parcels
   - Structural connectome construction (streamline counts vs. weighted metrics)
   - Graph-theoretic measures (degree, betweenness, small-worldness, clustering)
   - Statistical methods appropriate for connectome comparison (permutation testing, NBS, TFCE)
   - Normative modelling of connectivity across age / sex / site

3. **Schema engineering** — If the project produces structured outputs (e.g., participant-level graph metrics, edge-level statistics), what does the ontology look like? What are the versioning rules? What Pydantic (or protobuf, or dataclass) patterns are appropriate?

4. **Data provenance and open-corpus strategy** — Which public datasets (HCP, UK Biobank, EPILEPSIAE, ABIDE, ADNI, CamCAN, PING) are candidates? What is each corpus's licence, access requirement, and quality caveat? What silver-vs-gold distinctions apply?

5. **Pipeline engineering** — QSIPrep? MRtrix3? FSL BedpostX? What are the standard containers (Docker / Apptainer), and how are their versions pinned? How are the intermediate artefacts (fibre-orientation distributions, streamlines, connectomes) organised on disk?

6. **Reproducibility** — Per-participant run manifest with software versions, seed values, parameter choices; container tags; commit SHAs of analysis code.

7. **Statistical engineering** — Multiple-comparison correction across edges (typically ~2,000–4,500 for DKT with 68 nodes), permutation-test setup, cluster-forming thresholds, confounder handling (age / sex / site / motion).

8. **Debugging methodology** — What kinds of failures are common in a connectome pipeline (QC failures, motion artefacts, segmentation errors, disconnected components), and how are they surfaced?

9. **Programming concepts as applied** — Adapt from `learning_medai.md` §13 with any DKT-connectome-specific patterns.

10. **Session-specific decisions and their rationale** — Every non-obvious choice made in the session, with the reasoning. Especially important when a reader wants to know "why did we do X and not Y?"

11. **What is NOT done and why** — Known unknowns and their gating conditions.

12. **Appendix: files at a glance** — Key repo paths.

13. **Appendix: commit sequence** — Commits in order, forming a design-evolution narrative.

## Cross-references to `learning_medai.md`

If the DKT-connectome project shares engineering patterns with MedAI-EPI, cite the MedAI section rather than duplicating. Common candidates for cross-reference:
- Pydantic v2 generics for evidence-wrapped values → `learning_medai.md` §3.1
- Prompt registry versioning → applicable if the DKT project uses LLMs at all
- Run-manifest pattern for per-inference reproducibility → `learning_medai.md` §10.1
- SLURM gotchas (venv activation, .env sourcing, bf16 for large models) → `learning_medai.md` §11.1

## Notes for the reader

- Keep the document a *teaching artefact*, not a diary. Each section should teach a transferable concept, not narrate the day.
- Cite specific commit hashes and file paths where possible so readers can go from concept to code in one click.
- End every §"decisions and rationale" bullet with *why the alternative was rejected* — that is often more instructive than the chosen approach.
- Version this document alongside the code; bump a small version marker at the top (e.g. `v0.1 draft`, `v0.2 with results`).

## Template metadata

- Template created: 2026-09-22
- Template author: Claude (Opus 4.7) working with `phindagiji@gmail.com`
- Companion document: `writing/learning_medai.md`
- Suggested target document version to bootstrap: v0.1 (draft, no results)

*End of template. Fill in above when DKT-connectome work begins.*
