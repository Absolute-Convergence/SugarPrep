"""Source-bound orchestration for the fourteen deterministic Cleaner tools."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from typing import Any, Callable

from sugarprep.domain.dataset import (
    CleanerExecutionEvidence,
    CleanerToolEvidence,
    DatasetProvenance,
    DatasetSnapshot,
)
from sugarprep.domain.errors import SugarPrepError
from sugarprep.domain.result import CleanerExecutionResult
from sugarprep.transforms.candidate_output import TransformCandidateOutput
from sugarprep.transforms.cleaner.input_port import CleanerPayloadInput, CleanerPlanCandidateInput
from sugarprep.transforms.cleaner.model import (
    CleanerStepOutcome,
    CleanerTable,
    CleanerToolError,
    parse_cleaner_table,
)
from sugarprep.transforms.cleaner.structure import (
    detect_file_format,
    flatten_multirow_header,
    normalize_column_names,
    repair_ragged_rows,
    select_header_row,
    trim_preamble_footer,
)
from sugarprep.transforms.cleaner.values import (
    deduplicate_rows,
    join_datetime_parts,
    normalize_missing_tokens,
    normalize_wide_periods,
    parse_datetime,
    parse_flexible_number,
    split_compound_column,
    validate_parseable_table,
)


class CleanerExecutionError(SugarPrepError):
    pass


AUTHORITATIVE_VALIDATION_CALL_ID = "cleaner-authoritative-validation"


CleanerToolHandler = Callable[[CleanerTable, dict[str, Any]], CleanerStepOutcome]


TOOL_HANDLERS: dict[str, CleanerToolHandler] = {
    "detect_file_format": detect_file_format,
    "select_header_row": select_header_row,
    "flatten_multirow_header": flatten_multirow_header,
    "trim_preamble_footer": trim_preamble_footer,
    "repair_ragged_rows": repair_ragged_rows,
    "normalize_column_names": normalize_column_names,
    "normalize_missing_tokens": normalize_missing_tokens,
    "parse_flexible_number": parse_flexible_number,
    "parse_datetime": parse_datetime,
    "join_datetime_parts": join_datetime_parts,
    "normalize_wide_periods": normalize_wide_periods,
    "split_compound_column": split_compound_column,
    "deduplicate_rows": deduplicate_rows,
    "validate_parseable_table": validate_parseable_table,
}


class CleanerExecutionPipeline:
    """Execute one strict model candidate without mutating or promoting its source."""

    def __init__(
        self,
        payload_input: CleanerPayloadInput,
        candidate_output: TransformCandidateOutput,
    ) -> None:
        self._payload_input = payload_input
        self._candidate_output = candidate_output

    def execute(
        self,
        *,
        input_snapshot: DatasetSnapshot,
        candidate: CleanerPlanCandidateInput,
    ) -> CleanerExecutionResult:
        if not isinstance(candidate, CleanerPlanCandidateInput):
            raise TypeError("candidate must satisfy CleanerPlanCandidateInput")
        if candidate.source_sha256 != input_snapshot.content_sha256:
            raise CleanerExecutionError("Cleaner candidate does not match the supplied source snapshot")
        self._payload_input.assert_unchanged(input_snapshot)
        plan = candidate.plan
        if plan.stop_reason != "execute":
            return CleanerExecutionResult(
                plan_candidate_id=candidate.candidate_id,
                provider_id=candidate.provider_id,
                plan_id=plan.plan_id,
                stop_reason=plan.stop_reason,
                input_snapshot=input_snapshot,
                unknowns=plan.unknowns,
                warnings=plan.warnings,
                diagnostics=plan.diagnostics,
                metadata=plan.metadata,
            )

        try:
            table = parse_cleaner_table(self._payload_input.read_text(input_snapshot))
            executions = self._execute_tools(table, candidate)
        except CleanerToolError as exc:
            raise CleanerExecutionError(str(exc)) from exc
        self._payload_input.assert_unchanged(input_snapshot)
        write_session = self._candidate_output.open_candidate(
            input_snapshot=input_snapshot,
            plan_id=plan.plan_id,
            headers=tuple(table.headers),
        )
        try:
            for row in table.data_rows:
                write_session.write_row(tuple(row.values))
            output_snapshot = write_session.commit()
        except Exception:
            write_session.abort()
            raise
        evidence = _execution_evidence(
            input_snapshot=input_snapshot,
            output_snapshot=output_snapshot,
            candidate=candidate,
            executions=executions,
        )
        output_snapshot = replace(
            output_snapshot,
            provenance=DatasetProvenance(
                operation=output_snapshot.provenance.operation,
                parent_sha256=output_snapshot.provenance.parent_sha256,
                cleaner_evidence=evidence,
            ),
        )
        return CleanerExecutionResult(
            plan_candidate_id=candidate.candidate_id,
            provider_id=candidate.provider_id,
            plan_id=plan.plan_id,
            stop_reason=plan.stop_reason,
            input_snapshot=input_snapshot,
            output_snapshot=output_snapshot,
            evidence=evidence,
            unknowns=plan.unknowns,
            warnings=plan.warnings,
            diagnostics=plan.diagnostics,
            metadata=plan.metadata,
        )

    @staticmethod
    def _execute_tools(
        table: CleanerTable,
        candidate: CleanerPlanCandidateInput,
    ) -> tuple[CleanerToolEvidence, ...]:
        completed: set[str] = set()
        evidence: list[CleanerToolEvidence] = []
        for index, call in enumerate(candidate.plan.tool_calls, start=1):
            call_id = call.call_id or f"cleaner-{index:03d}"
            if call_id == AUTHORITATIVE_VALIDATION_CALL_ID:
                raise CleanerToolError(
                    f"Cleaner plan uses reserved call_id {AUTHORITATIVE_VALIDATION_CALL_ID}"
                )
            if call_id in completed:
                raise CleanerToolError(f"Cleaner plan repeats call_id {call_id}")
            missing = [precondition for precondition in call.preconditions if precondition not in completed]
            if missing:
                raise CleanerToolError(
                    f"Cleaner call {call_id} has unmet preconditions: " + ", ".join(missing)
                )
            handler = TOOL_HANDLERS.get(call.tool_name)
            if handler is None:
                raise CleanerToolError(f"Cleaner tool has no deterministic handler: {call.tool_name}")
            try:
                outcome = handler(table, call.arguments)
            except CleanerToolError:
                raise
            except (KeyError, TypeError, ValueError) as exc:
                raise CleanerToolError(f"Cleaner tool {call.tool_name} failed: {exc}") from exc
            evidence.append(_tool_evidence(call_id, call.tool_name, call.arguments, outcome))
            completed.add(call_id)

        validation = validate_parseable_table(table, {})
        evidence.append(
            _tool_evidence(
                AUTHORITATIVE_VALIDATION_CALL_ID,
                "validate_parseable_table",
                {},
                validation,
            )
        )
        return tuple(evidence)


def _tool_evidence(
    call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    outcome: CleanerStepOutcome,
) -> CleanerToolEvidence:
    return CleanerToolEvidence(
        call_id=call_id,
        tool_name=tool_name,
        arguments=arguments,
        rows_input=outcome.rows_input,
        rows_output=outcome.rows_output,
        rows_quarantined=outcome.rows_quarantined,
        details=outcome.details,
    )


def _execution_evidence(
    *,
    input_snapshot: DatasetSnapshot,
    output_snapshot: DatasetSnapshot,
    candidate: CleanerPlanCandidateInput,
    executions: tuple[CleanerToolEvidence, ...],
) -> CleanerExecutionEvidence:
    payload = {
        "plan_candidate_id": candidate.candidate_id,
        "provider_id": candidate.provider_id,
        "plan_id": candidate.plan.plan_id,
        "input_sha256": input_snapshot.content_sha256,
        "output_sha256": output_snapshot.content_sha256,
        "tool_executions": [
            {
                "call_id": item.call_id,
                "tool_name": item.tool_name,
                "arguments": item.arguments,
                "rows_input": item.rows_input,
                "rows_output": item.rows_output,
                "rows_quarantined": item.rows_quarantined,
                "details": item.details,
            }
            for item in executions
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return CleanerExecutionEvidence(
        evidence_id=f"cleaner-execution-{hashlib.sha256(encoded).hexdigest()[:24]}",
        plan_candidate_id=candidate.candidate_id,
        provider_id=candidate.provider_id,
        plan_id=candidate.plan.plan_id,
        input_sha256=input_snapshot.content_sha256,
        output_sha256=output_snapshot.content_sha256,
        tool_executions=executions,
        rows_quarantined=sum(item.rows_quarantined for item in executions),
        validation_passed=True,
    )
