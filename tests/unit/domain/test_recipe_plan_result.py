from __future__ import annotations

import pytest

from sugarprep.domain import (
    DatasetRef,
    DatasetSnapshot,
    DiagnosticSeverity,
    DomainValidationError,
    Layout,
    OutputColumn,
    PreparationDiagnostic,
    PreparationPlan,
    PreparationResult,
    Recipe,
)


def _reference() -> DatasetRef:
    return DatasetRef(dataset_id="sales", storage_locator="source:active")


def _snapshot(digest: str = "a") -> DatasetSnapshot:
    return DatasetSnapshot(
        reference=_reference(),
        content_sha256=digest * 64,
        media_type="text/csv",
        headers=("date", "amount"),
        row_count=10,
    )


def _layout() -> Layout:
    return Layout(
        time_column="date",
        time_kind="YYYY-MM-DD",
        value_columns=("amount",),
        primary_value_column="amount",
    )


def _columns() -> tuple[OutputColumn, ...]:
    return (
        OutputColumn(name="date", source="date"),
        OutputColumn(name="amount", source="amount"),
    )


def test_recipe_plan_and_result_are_distinct_contracts() -> None:
    recipe = Recipe(
        version=1,
        name="sales-cleanup",
        output_columns=_columns(),
        layout=_layout(),
        expected_headers=("date", "amount"),
    )
    plan = PreparationPlan(
        plan_id="plan-1",
        version=recipe.version,
        recipe_name=recipe.name,
        input_snapshot=_snapshot(),
        output_columns=recipe.output_columns,
        layout=recipe.layout,
        row_rules=recipe.row_rules,
        reject_policy=recipe.reject_policy,
    )
    result = PreparationResult(
        plan_id=plan.plan_id,
        input_snapshot=plan.input_snapshot,
        output_snapshot=_snapshot("b"),
        diagnostics=(
            PreparationDiagnostic(
                code="rows.prepared",
                message="Preparation completed.",
                severity=DiagnosticSeverity.INFO,
            ),
        ),
    )

    assert result.completed
    assert not result.has_errors
    assert not hasattr(result, "accept")
    assert not hasattr(result, "artifact_bundle")


def test_layout_rejects_primary_value_outside_values() -> None:
    with pytest.raises(DomainValidationError, match="included"):
        Layout(
            time_column="date",
            time_kind="YYYY-MM-DD",
            value_columns=("amount",),
            primary_value_column="price",
        )
