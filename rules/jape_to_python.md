# JAPE → Python (spaCy Matcher + medspaCy ConText) cheatsheet

MedAI-EPI Phase 2 — one-page port guide for the ExECT-V2 JAPE study. We are
NOT running JAPE / GATE / Groovy; we mimic the semantics with `spacy.Matcher`,
`spacy.tokens.Doc`, medspaCy `ConText`, and Pydantic-validated `Evidence[T]`.

## 1. Files & entry points

| JAPE / GATE                                | Python equivalent                                    |
| ------------------------------------------ | ---------------------------------------------------- |
| `*.jape` phase file                        | one `BaseFieldRule` subclass in `rules/…`            |
| GATE pipeline (`*.gapp`)                   | `services/phenotype_assembler.py`                    |
| GATE `AnnotationSet`                       | `list[LinkedEntity]` (from MedCAT) + spaCy `Doc.ents` |
| GATE `Annotation` (`{type, features, …}`)  | `LinkedEntity` dataclass                             |
| Groovy `SerializeGate` / XML dump          | `EpilepsyPhenotype.model_dump_json()`                |

## 2. Rule syntax

```jape
Rule: FocalSeizure
Priority: 100
(
  {Lookup.majorType == "seizure_type", Lookup.minorType == "focal"}
  ({Space})? {Lookup.majorType == "laterality"}
):match
--> :match.SeizureMention = {seizure_type = "focal", …}
```

Python equivalent:

```python
class FocalSeizureRule(BaseFieldRule):
    field_name = "clinical_seizure.predominant_seizure_type"
    enum_class = SeizureType

    def apply(self, entities, doc, meta):
        # Lookup.majorType == "seizure_type"
        cands = [e for e in self.relevant_entities(entities)
                 if e.enum_value.startswith("focal_")]
        for e in cands:
            if e.is_negated or e.is_hypothetical:
                continue  # ConText handles what JAPE did with hedge phases
            return self._make_evidence(SeizureType(e.enum_value), e, meta)
        return None
```

## 3. Construct-by-construct port table

| JAPE construct                              | Python replacement                                                     |
| ------------------------------------------- | ---------------------------------------------------------------------- |
| `Rule: Name / Priority: N`                  | one `BaseFieldRule` subclass; ordering handled by registry             |
| `{Lookup.majorType == "X"}`                 | `[e for e in entities if e.enum_class == "X"]`                         |
| `{Lookup.majorType == "X", Lookup.minorType == "y"}` | filter by `e.enum_class == "X" and e.enum_value == "y"`      |
| `{Token.string == "seizure"}`               | spaCy `Matcher` with `[{"LOWER": "seizure"}]`                          |
| `{Token.category == "N.*"}` (regex)         | `Matcher` with `[{"TAG": {"REGEX": "^N"}}]`                            |
| Concatenation `A B` (adjacent)              | Matcher pattern list; MedCAT already merges multi-word names           |
| Alternation `A \| B`                        | one `Matcher` pattern per alternative, or `{"IN": [...]}` on token    |
| Kleene star `A*` / plus `A+`                | Matcher token op `"OP": "*"` / `"OP": "+"`                             |
| Optional `A?`                               | `"OP": "?"`                                                            |
| `({X})[range]:label`                        | callback `on_match=lambda matcher, doc, i, matches: …`                 |
| `:label` binding                            | Python variable holding the matched `Span`                             |
| `--> :label.Y = {a=b}` (post-condition)     | builder that returns `Evidence[T]` with fields                         |
| JAPE macros (`Macro: FOO`)                  | Python helper function (module scope)                                  |
| `Split` (sentence boundary)                 | `doc.sents` (medspaCy sentencizer already set)                         |
| Phase ordering (BrillTagger → ConText → …)  | `Language.pipe_names` order in `build_medspacy_pipeline()`             |
| JAPE `Priority` / firstMatch policy         | rule registry runs first-hit or highest-priority per field (Phase 3)   |

## 4. GATE ConText features → medspaCy ConText attributes

ExECT-V2 emits GATE features via `Tagger_ConText`. medspaCy attaches the
equivalent attributes to `Span` / `Token` via `._.` and — for our pipeline —
we lift them onto each `LinkedEntity`.

| GATE feature                        | medspaCy attribute (default map)  | `LinkedEntity` field  |
| ----------------------------------- | --------------------------------- | --------------------- |
| `Negation="AFFIRMED"/"NEGATED"`     | `NEGATED_EXISTENCE → is_negated`  | `is_negated`          |
| `Temporality="HISTORICAL"`          | `HISTORICAL → is_historical`      | `is_historical`       |
| `Temporality="HYPOTHETICAL"`        | `HYPOTHETICAL → is_hypothetical`  | `is_hypothetical`     |
| `Experiencer="Family"`              | `FAMILY → is_family`              | `is_family`           |
| `Certainty="POSSIBLE"`              | `POSSIBLE_EXISTENCE → is_uncertain` | (drives `Certainty.POSSIBLE` in Phase 3) |
| pseudo-negation (e.g. "no change")  | `direction="PSEUDO"` in ConTextRule | prevents false NEG   |
| termination ("but", "however")      | `direction="TERMINATE"`           | scope-limiting only   |

## 5. Post-condition serializer → Pydantic `Evidence[T]`

JAPE:

```jape
--> :label.SeizureMention = {
      seizure_type = "focal_impaired_awareness",
      certainty    = "DEFINITE",
      evidence     = :label.@string,
      offset_start = :label.@start
    }
```

Python (via `BaseFieldRule._make_evidence`):

```python
Evidence[SeizureType](
    value=SeizureType.FOCAL_IMPAIRED_AWARENESS,
    certainty=Certainty.DEFINITE,        # downgraded by ConText if is_uncertain
    temporal_status=TemporalStatus.CURRENT,  # or HISTORICAL if is_historical
    evidence_text=doc.text[e.char_start:e.char_end],
    source_doc_id=meta["doc_id"],
    source_doc_type=meta["doc_type"],
    source_date=meta["doc_date"],
    char_start=e.char_start,
    char_end=e.char_end,
)
```

## 6. Idioms we deliberately drop

- **`Priority: N` numeric priorities**: replaced by explicit per-field
  registry keyed by `field_name`. If two rules match, first non-`None`
  result wins; ties are broken by rule registration order.
- **GATE Java macros / groovy scriptlets**: everything is Python.
- **XML gazetteer format**: our gazetteers live in `rules/epilepsy_ontology.py`
  as typed `ConceptEntry` records with `synonyms` lists.

## 7. What we do NOT copy from ExECT

We read ExECT's `Tagger_ConText/resources/gazetteers/triggers/*.lst`
(432 lines total) to understand which negation / hedging phrases they cover.
We adopt medspaCy's default rule set (US-VA tuned, 102 rules) plus a small
set of clinical-experience additions (see `rules/context_config.py`).
We do NOT copy the ExECT trigger lists verbatim into our tree.
