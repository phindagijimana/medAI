#!/usr/bin/env python3
"""Generate rules/asm_lexicon.py from the pinned RxNorm release.

Selection
---------
* every ingredient under WHO ATC N03A (antiepileptics), minus combination
  pseudo-ingredients and GABA itself;
* every drug already curated in rules.epilepsy_ontology.MEDICATION_ONTOLOGY
  (gabapentin and pregabalin moved to ATC N02BF in 2023);
* EXTRA_INGREDIENTS: drugs with a US FDA seizure indication that ATC files
  outside N03A — rescue benzodiazepines (diazepam rectal/nasal, midazolam
  nasal: seizure clusters; lorazepam injection: status epilepticus) and
  adjuncts (clorazepate: partial seizures; acetazolamide: centrencephalic
  epilepsies; corticotropin: infantile spasms; everolimus: TSC-associated
  partial-onset seizures).  Label sources: docs/ONTOLOGY_SOURCES.md.

For each ingredient we record the RxNorm RXCUI, ATC codes, the SNOMED CT
substance concept RxNorm links to it, salt forms (PIN) and single-ingredient
brand names (BN).  Only RxNorm-native strings (SAB=RXNORM, public domain) are
written out; ATC and SNOMED contribute identifiers only.

    venv/bin/python scripts/build_asm_lexicon.py            # writes rules/asm_lexicon.py
    venv/bin/python scripts/build_asm_lexicon.py --dry-run  # print, don't write
"""

from __future__ import annotations

import argparse
import pprint
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from services.ontology_releases import release_path, release_tag  # noqa: E402

OUT = REPO / "rules" / "asm_lexicon.py"

ATC_PREFIX = "N03A"
ATC_EXCLUDE = re.compile(r"combinations|^aminobutyric acid$")

# RxNorm ingredient name → role
EXTRA_INGREDIENTS: dict[str, str] = {
    "diazepam": "rescue",
    "lorazepam": "rescue",
    "midazolam": "rescue",
    "clorazepate": "adjunct",
    "acetazolamide": "adjunct",
    "corticotropin": "adjunct",
    "everolimus": "adjunct",
}

# Brand names that are ordinary words or too ambiguous to match on in notes.
BRAND_STOPLIST = {
    "equetro", "luminal", "solfoton", "sezaby", "intensol",
}
_MIN_BRAND_LEN = 4


def _curated() -> dict[str, list[str]]:
    from rules.epilepsy_ontology import MEDICATION_ONTOLOGY
    return {
        key: [e.label, *e.synonyms]
        for key, e in MEDICATION_ONTOLOGY.items()
        if "generated:asm_lexicon" not in e.source_provenance
    }


def build() -> dict[str, dict]:
    rrf = release_path("rxnorm") / "rrf"

    rx_names: dict[str, tuple[str, str]] = {}     # rxcui → (TTY, str) for IN/PIN/BN
    atc: dict[str, list[str]] = defaultdict(list)
    atc_name: dict[str, str] = {}
    sct_substance: dict[str, str] = {}
    with (rrf / "RXNCONSO.RRF").open(encoding="utf-8") as f:
        for line in f:
            c = line.split("|")
            cui, sab, tty, code, s, suppress = c[0], c[11], c[12], c[13], c[14], c[16]
            if sab == "RXNORM" and tty in ("IN", "PIN", "BN") and suppress == "N":
                rx_names.setdefault(cui, (tty, s))
            elif sab == "ATC" and tty == "IN" and len(code) == 7:
                atc[cui].append(code)
                atc_name[cui] = s
            elif sab == "SNOMEDCT_US" and tty == "FN" and s.endswith("(substance)"):
                sct_substance.setdefault(cui, code)

    def tty(cui: str) -> str:
        return rx_names.get(cui, ("",))[0]

    pin_to_in: dict[str, str] = {}
    brand_ingredients: dict[str, set[str]] = defaultdict(set)
    with (rrf / "RXNREL.RRF").open(encoding="utf-8") as f:
        for line in f:
            c = line.split("|")
            if c[10] != "RXNORM":
                continue
            rela, a, b = c[7], c[0], c[4]
            if rela in ("has_form", "form_of", "has_tradename", "tradename_of"):
                for ing, other in ((a, b), (b, a)):
                    if tty(ing) != "IN":
                        continue
                    if tty(other) == "PIN":
                        pin_to_in.setdefault(other, ing)
                    elif tty(other) == "BN":
                        brand_ingredients[other].add(ing)

    # ATC sometimes points at a salt form (valproic acid is a PIN of valproate).
    def ingredient(cui: str) -> str | None:
        return cui if tty(cui) == "IN" else pin_to_in.get(cui)

    by_name = {s.lower(): ingredient(cui) for cui, (t, s) in rx_names.items() if t in ("IN", "PIN")}

    wanted: dict[str, tuple[str, str | None]] = {}   # rxcui → (role, curated key)
    for cui, codes in atc.items():
        ing = ingredient(cui)
        if ing and any(code.startswith(ATC_PREFIX) for code in codes) \
                and not ATC_EXCLUDE.search(atc_name[cui]):
            wanted[ing] = ("asm", None)
    for name, role in EXTRA_INGREDIENTS.items():
        cui = by_name.get(name)
        if not cui:
            raise SystemExit(f"EXTRA_INGREDIENTS: {name!r} is not an RxNorm ingredient")
        wanted[cui] = (role, None)
    # A curated entry can span several RxNorm ingredients; the first match is
    # primary and the rest fold into it.
    alt_of: dict[str, str] = {}
    for key, names in _curated().items():
        cuis = list(dict.fromkeys(by_name[n.lower()] for n in names if by_name.get(n.lower())))
        if not cuis:
            raise SystemExit(f"curated medication {key!r} has no RxNorm ingredient match")
        role = wanted.get(cuis[0], ("asm", None))[0]
        wanted[cuis[0]] = (role, key)
        for alt in cuis[1:]:
            wanted.pop(alt, None)
            alt_of[alt] = cuis[0]

    salts: dict[str, set[str]] = defaultdict(set)
    for pin, ing in pin_to_in.items():
        ing = ing if ing in wanted else alt_of.get(ing)
        if ing:
            salts[ing].add(rx_names[pin][1])

    brands: dict[str, set[str]] = defaultdict(set)
    for bn, ings in brand_ingredients.items():
        if len(ings) != 1:
            continue
        ing = next(iter(ings))
        ing = ing if ing in wanted else alt_of.get(ing)
        name = rx_names[bn][1]
        if ing and len(name) >= _MIN_BRAND_LEN and name.lower() not in BRAND_STOPLIST:
            brands[ing].add(name)

    atc_codes: dict[str, set[str]] = defaultdict(set)
    atc_names: dict[str, set[str]] = defaultdict(set)
    for cui, codes in atc.items():
        ing = ingredient(cui)
        ing = ing if ing in wanted else alt_of.get(ing)
        if ing:
            atc_codes[ing].update(codes)
            atc_names[ing].add(atc_name[cui])

    out: dict[str, dict] = {}
    for cui, (role, curated_key) in wanted.items():
        label = rx_names[cui][1]
        key = curated_key or re.sub(r"\W+", "_", label.lower()).strip("_")
        alts = sorted(a for a, p in alt_of.items() if p == cui)
        extra_names = {rx_names[a][1] for a in alts} | atc_names[cui]
        extra_names = {n for n in extra_names if n.lower() != label.lower()}
        out[key] = {
            "rxcui": cui,
            "alt_rxcuis": alts,
            "label": label,
            "role": role,
            "atc": sorted(atc_codes[cui]),
            "sctid": sct_substance.get(cui),
            "salts": sorted(salts[cui]),
            "brands": sorted(brands[cui]),
            "other_names": sorted(n for n in extra_names if n.lower() not in {s.lower() for s in salts[cui]}),
            "curated": curated_key is not None,
        }
    return dict(sorted(out.items()))


def write(lexicon: dict[str, dict]) -> None:
    body = pprint.pformat(lexicon, width=100, sort_dicts=False)
    OUT.write_text(
        '"""Anti-seizure medication lexicon. Generated by scripts/build_asm_lexicon.py\n'
        f"from {release_tag('rxnorm')}; do not edit by hand.\n\n"
        "role: 'asm' (ATC N03A or curated ASM), 'rescue' (benzodiazepine rescue),\n"
        "      'adjunct' (FDA seizure indication outside ATC N03A, e.g. ACTH, everolimus).\n"
        '"""\n\n'
        f"RXNORM_RELEASE = {release_tag('rxnorm')!r}\n\n"
        f"ASM_LEXICON: dict[str, dict] = {body}\n",
        encoding="utf-8",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    lex = build()
    for key, d in lex.items():
        print(f"{key:28s} {d['rxcui']:>8s} {d['role']:8s} {','.join(d['atc']) or '-':18s} "
              f"sct={d['sctid'] or '-':>10s} brands={d['brands']} salts={d['salts']}")
    print(f"{len(lex)} ingredients ({sum(not d['curated'] for d in lex.values())} new)")
    if not args.dry_run:
        write(lex)
        print(f"wrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
