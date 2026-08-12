from __future__ import annotations

import pytest

from sugarprep.transforms.cells import apply_transform
from sugarprep.transforms.derivation import derive_value
from sugarprep.transforms.rows import RowRuleViolation, check_row_rule


def test_scalar_transforms_preserve_legacy_deterministic_behavior() -> None:
    assert apply_transform("trim", "  hello  ", "name") == "hello"
    assert apply_transform("parse_flexible_number", "($1.25K)", "amount") == "-1250"
    assert apply_transform("parse_flexible_number", "25%", "ratio", {"percent": "fraction"}) == "0.25"
    assert apply_transform("parse_date", "20260809", "date") == "2026-08-09"
    assert apply_transform("map_values", "Y", "flag", {"mapping": {"Y": "yes"}}) == "yes"


def test_missing_values_are_resolved_before_scalar_transform() -> None:
    assert apply_transform("parse_numeric", " NA ", "amount", {"missing_tokens": ("NA",)}) == ""


def test_derivations_use_only_explicit_sources_and_parameters() -> None:
    values = {"year": "2026", "month": "8", "day": "9"}

    assert derive_value("join", values, "key", {"separator": "-"}) == "2026-8-9"
    assert derive_value("template", values, "key", {"template": "{year}/{month}/{day}"}) == "2026/8/9"
    assert (
        derive_value(
            "datetime_parts",
            values,
            "date",
            {"year": "year", "month": "month", "day": "day", "output_format": "%Y-%m-%d"},
        )
        == "2026-08-09"
    )


def test_row_rules_distinguish_data_violations_from_configuration_errors() -> None:
    with pytest.raises(RowRuleViolation, match="negative"):
        check_row_rule("nonnegative", "-1", "amount")

    with pytest.raises(ValueError, match="values sequence"):
        check_row_rule("allowed_values", "x", "kind", {"values": "x"})
