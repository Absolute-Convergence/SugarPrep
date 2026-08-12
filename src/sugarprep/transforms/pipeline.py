"""Storage-independent deterministic preparation-plan execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sugarprep.domain.plan import PreparationPlan
from sugarprep.domain.recipe import OutputColumn
from sugarprep.domain.result import (
    DiagnosticSeverity,
    PreparationDiagnostic,
    PreparationResult,
    RejectedRow,
)
from sugarprep.transforms.candidate_output import TransformCandidateOutput
from sugarprep.transforms.cells import apply_transform
from sugarprep.transforms.derivation import derive_value
from sugarprep.transforms.payload_input import TransformPayloadInput
from sugarprep.transforms.rows import RowRuleViolation, check_row_rule


@dataclass(frozen=True, slots=True)
class ColumnTransformError(Exception):
    output_column: str
    operation: str
    reason: str

    def __str__(self) -> str:
        return f"{self.output_column} failed {self.operation}: {self.reason}"


class TransformPipeline:
    """Execute a compiled plan without interpreting storage locators."""

    def __init__(self, payload_input: TransformPayloadInput, candidate_output: TransformCandidateOutput) -> None:
        self._payload_input = payload_input
        self._candidate_output = candidate_output

    def execute(self, plan: PreparationPlan) -> PreparationResult:
        self._payload_input.assert_unchanged(plan.input_snapshot)
        headers = tuple(column.name for column in plan.output_columns)
        input_headers = plan.input_snapshot.headers
        rejected_rows: list[RejectedRow] = []
        warnings: list[str] = []
        candidate = self._candidate_output.open_candidate(
            input_snapshot=plan.input_snapshot,
            plan_id=plan.plan_id,
            headers=headers,
        )
        try:
            for source_row_number, values in enumerate(
                self._payload_input.iter_rows(plan.input_snapshot),
                start=1,
            ):
                if len(values) != len(input_headers):
                    candidate.abort()
                    return _fatal_result(
                        plan,
                        code="transform.input_shape_mismatch",
                        message=(
                            f"source row {source_row_number} has {len(values)} values; "
                            f"expected {len(input_headers)}"
                        ),
                        rejected_rows=rejected_rows,
                        warnings=warnings,
                    )
                source_row = dict(zip(input_headers, values, strict=True))
                try:
                    output_row = _build_output_row(plan, source_row, source_row_number)
                    row_warnings = _evaluate_row_rules(plan, output_row)
                except (ColumnTransformError, RowRuleViolation, ValueError) as exc:
                    rejected_rows.append(
                        RejectedRow(
                            source_row_number=source_row_number,
                            reason_code=_rejection_code(exc),
                            message=str(exc),
                        )
                    )
                    if plan.reject_policy == "fail":
                        candidate.abort()
                        return _fatal_result(
                            plan,
                            code="transform.row_rejected",
                            message=f"source row {source_row_number} was rejected: {exc}",
                            rejected_rows=rejected_rows,
                            warnings=warnings,
                        )
                    continue
                warnings.extend(f"source row {source_row_number}: {warning}" for warning in row_warnings)
                candidate.write_row(tuple(output_row[header] for header in headers))

            self._payload_input.assert_unchanged(plan.input_snapshot)
            output_snapshot = candidate.commit()
        except Exception:
            candidate.abort()
            raise
        return PreparationResult(
            plan_id=plan.plan_id,
            input_snapshot=plan.input_snapshot,
            output_snapshot=output_snapshot,
            rejected_rows=tuple(rejected_rows),
            warnings=tuple(warnings),
        )


def _build_output_row(
    plan: PreparationPlan,
    source_row: Mapping[str, str],
    source_row_number: int,
) -> dict[str, str]:
    output: dict[str, str] = {}
    for column in plan.output_columns:
        value = _initial_value(column, source_row, source_row_number)
        for step in column.transforms:
            parameters = {"missing_tokens": plan.layout.missing_tokens, **dict(step.parameters)}
            try:
                value = apply_transform(step.name, value, column.name, parameters)
            except ValueError as exc:
                raise ColumnTransformError(column.name, step.name, str(exc)) from exc
        output[column.name] = value
    return output


def _initial_value(
    column: OutputColumn,
    source_row: Mapping[str, str],
    source_row_number: int,
) -> str:
    if column.generate == "row_index":
        return str(source_row_number)
    if column.source is not None:
        return source_row[column.source]
    if column.sources:
        source_values = {source: source_row[source] for source in column.sources}
        try:
            return derive_value(
                column.derive or "join",
                source_values,
                column.name,
                column.derive_parameters,
            )
        except ValueError as exc:
            raise ColumnTransformError(column.name, column.derive or "join", str(exc)) from exc
    raise ColumnTransformError(column.name, "generate", "unsupported generated column")


def _evaluate_row_rules(plan: PreparationPlan, output_row: Mapping[str, str]) -> tuple[str, ...]:
    warnings: list[str] = []
    for rule in plan.row_rules:
        parameters: dict[str, Any] = {
            "missing_tokens": plan.layout.missing_tokens,
            **dict(rule.parameters),
        }
        try:
            check_row_rule(rule.name, output_row[rule.column], rule.column, parameters)
        except RowRuleViolation as exc:
            if rule.action == "warn":
                warnings.append(str(exc))
                continue
            raise
    return tuple(warnings)


def _fatal_result(
    plan: PreparationPlan,
    *,
    code: str,
    message: str,
    rejected_rows: list[RejectedRow],
    warnings: list[str],
) -> PreparationResult:
    return PreparationResult(
        plan_id=plan.plan_id,
        input_snapshot=plan.input_snapshot,
        output_snapshot=None,
        rejected_rows=tuple(rejected_rows),
        warnings=tuple(warnings),
        diagnostics=(
            PreparationDiagnostic(
                code=code,
                message=message,
                severity=DiagnosticSeverity.ERROR,
            ),
        ),
    )


def _rejection_code(error: Exception) -> str:
    if isinstance(error, ColumnTransformError):
        return "transform.column_failed"
    if isinstance(error, RowRuleViolation):
        return f"transform.row_rule.{error.rule}"
    return "transform.row_rule_configuration"
