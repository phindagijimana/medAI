"""Optional patient-level roll-up of a LEO result.

LEO answers per note: every row of the input is one note and gets its own values.  That is the default and nothing
here changes it.  When a user says that several notes belong to one patient, ``rollup`` makes one row per patient
from the per-note result, with a plain rule:

* per field, the value comes from the **latest note that states one** (latest by ``date_col`` when given, else the
  later row), so an earlier note fills a field the latest note is silent on;
* values from different notes are never mixed inside one field (a drug list is the latest note's list, not a union);
* every value says which row and date it came from, and its status, why and evidence are copied unchanged;
* nothing is voted on or averaged, and the status is never upgraded (a value that needed review still does).

Which note is "right" for a field that changed over time (seizure frequency, current drugs) is a clinical choice:
this is the simple one, and the per-note table stays available beside it.
"""

from __future__ import annotations

import pandas as pd

from services.leo_review import NOT_REVIEWABLE, Field, infer_fields


def rollup(table: pd.DataFrame, patient_col: str, date_col: str = "", fields: list[Field] | None = None) -> pd.DataFrame:
    if patient_col not in table.columns:
        raise ValueError(f"no column {patient_col!r} in the table; columns: {', '.join(table.columns[:12])} ...")
    if date_col and date_col not in table.columns:
        raise ValueError(f"no column {date_col!r} in the table")
    fields = fields if fields is not None else infer_fields(table)
    t = table.copy()
    t["_row"] = range(1, len(t) + 1)
    t["_when"] = pd.to_datetime(t[date_col], errors="coerce") if date_col else pd.NaT
    out = []
    for pid, g in t.groupby(patient_col, sort=False):
        g = g.sort_values(["_when", "_row"], ascending=[False, False], na_position="last") if date_col else \
            g.sort_values("_row", ascending=False)
        rec = {patient_col: pid, "leo_notes": len(g), "leo_latest_row": int(g["_row"].iloc[0])}
        for f in fields:
            pick = next((r for _, r in g.iterrows() if str(r.get(f.status, "")) not in NOT_REVIEWABLE), None)
            if pick is None:
                rec.update({f.value: "", f"{f.value}_status": "not_found", f"{f.value}_from_row": "",
                            f"{f.value}_from_date": "", f"{f.value}_why": "", f"{f.value}_evidence": ""})
                continue
            rec.update({f.value: pick[f.value], f"{f.value}_status": pick[f.status], f"{f.value}_from_row": int(pick["_row"]),
                        f"{f.value}_from_date": "" if pd.isna(pick["_when"]) else str(pick["_when"].date()),
                        f"{f.value}_why": pick.get(f.why, "") if f.why else "",
                        f"{f.value}_evidence": pick.get(f.evidence, "")})
        out.append(rec)
    return pd.DataFrame(out)


__all__ = ["rollup"]
