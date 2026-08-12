from __future__ import annotations

import pytest

from sugarprep.domain import ColumnProfile, DatasetProfile, DatasetRef, DatasetSnapshot
from sugarprep.planning import PlanCompilationError, RecipeDocumentError, compile_recipe, parse_recipe


RECIPE = """
version: 1
name: sales-cleanup
input:
  expected_headers: [date, amount]
output:
  columns:
    - name: date
      source: date
      transform: trim
    - name: amount
      source: amount
      transform: parse_numeric
layout:
  time_col: date
  time_kind: YYYY-MM-DD
  value_cols: [amount]
  primary_value_col: amount
row_rules:
  - name: required
    column: date
reject_policy: fail
"""


def _profile(headers: tuple[str, ...] = ("date", "amount")) -> DatasetProfile:
    snapshot = DatasetSnapshot(
        reference=DatasetRef(dataset_id="sales", storage_locator="opaque-token"),
        content_sha256="a" * 64,
        media_type="text/csv",
        headers=headers,
        row_count=2,
    )
    return DatasetProfile(
        profile_id="profile-1",
        snapshot=snapshot,
        columns=tuple(ColumnProfile(name=header, row_count=2, missing_count=0) for header in headers),
        profiled_row_count=2,
    )


def test_parse_and_compile_are_explicit_and_deterministic() -> None:
    recipe = parse_recipe(RECIPE)
    first = compile_recipe(recipe, _profile())
    second = compile_recipe(recipe, _profile())

    assert recipe.expected_headers == ("date", "amount")
    assert first.plan_id == second.plan_id
    assert first.input_snapshot.content_sha256 == "a" * 64


def test_recipe_document_rejects_storage_paths() -> None:
    with pytest.raises(RecipeDocumentError, match="source paths"):
        parse_recipe("version: 1\nname: bad\nsource:\n  path: data.csv\n")


def test_compiler_rejects_profile_header_mismatch() -> None:
    with pytest.raises(PlanCompilationError, match="expected_headers"):
        compile_recipe(parse_recipe(RECIPE), _profile(("date", "price")))


def test_compiler_rejects_unknown_transform_without_importing_transforms() -> None:
    document = RECIPE.replace("parse_numeric", "invent_values")
    with pytest.raises(PlanCompilationError, match="unsupported transform"):
        compile_recipe(parse_recipe(document), _profile())
