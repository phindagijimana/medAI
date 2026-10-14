"""Current-ASM display views. Extract columns stay as they are."""
from __future__ import annotations

import pandas as pd
import pytest

from services.leo_asm_view import apply_asm_view, apply_asm_view_row, parse_asm_view, union_display


def test_parse_and_union():
    assert parse_asm_view("maintenance") == "maintenance"
    assert parse_asm_view("rescue") == "rescue-as-current"
    with pytest.raises(ValueError):
        parse_asm_view("vote")
    assert union_display("lamotrigine", "midazolam") == "lamotrigine; midazolam"
    assert union_display("lamotrigine; midazolam", "midazolam") == "lamotrigine; midazolam"


def test_row_and_table_do_not_overwrite_extract():
    row = apply_asm_view_row(
        {"current_asms": "lamotrigine", "rescue_medication": "midazolam"}, "rescue-as-current")
    assert row["current_asms"] == "lamotrigine"
    assert row["rescue_medication"] == "midazolam"
    assert row["asm_view"] == "rescue-as-current"
    assert row["current_asms_view"] == "lamotrigine; midazolam"
    maint = apply_asm_view_row(row, "maintenance")
    assert maint["current_asms_view"] == "lamotrigine"
    t = apply_asm_view(pd.DataFrame([{"current_asms": "lamotrigine", "rescue_medication": "midazolam"}]),
                       "rescue-as-current")
    assert t.loc[0, "current_asms"] == "lamotrigine"
    assert t.loc[0, "current_asms_view"] == "lamotrigine; midazolam"
