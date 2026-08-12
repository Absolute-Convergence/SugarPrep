"""Deterministic validation of one preparation result."""

from __future__ import annotations

import hashlib
import json

from sugarprep.domain.plan import PreparationPlan
from sugarprep.domain.result import PreparationResult
from sugarprep.validation.payload_input import ValidationPayloadInput
from sugarprep.validation.reports import ResultValidationReport, ValidationFinding


class ResultValidator:
    def __init__(self, payload_input: ValidationPayloadInput) -> None:
        self._payload_input = payload_input

    def validate(self, result: PreparationResult, plan: PreparationPlan) -> ResultValidationReport:
        findings: list[ValidationFinding] = []
        if result.plan_id != plan.plan_id:
            findings.append(ValidationFinding("result.plan_mismatch", "result does not belong to the plan"))
        if result.input_snapshot != plan.input_snapshot:
            findings.append(
                ValidationFinding("result.input_mismatch", "result input does not match the plan snapshot")
            )
        if result.has_errors:
            findings.append(ValidationFinding("result.execution_error", "execution reported an error"))
        if result.output_snapshot is None:
            findings.append(ValidationFinding("result.output_missing", "execution produced no candidate output"))
        else:
            output = result.output_snapshot
            expected_headers = tuple(column.name for column in plan.output_columns)
            if output.headers != expected_headers:
                findings.append(
                    ValidationFinding("result.headers_mismatch", "candidate headers do not match the plan")
                )
            if output.provenance.parent_sha256 != (plan.input_snapshot.content_sha256,):
                findings.append(
                    ValidationFinding(
                        "result.provenance_mismatch",
                        "candidate provenance does not identify the exact input snapshot",
                    )
                )
            try:
                self._payload_input.assert_unchanged(output)
                rows = tuple(self._payload_input.iter_rows(output))
            except Exception as exc:
                findings.append(
                    ValidationFinding("result.payload_unreadable", f"candidate payload validation failed: {exc}")
                )
            else:
                if any(len(row) != len(expected_headers) for row in rows):
                    findings.append(
                        ValidationFinding("result.row_shape_mismatch", "candidate contains a malformed row")
                    )
                if output.row_count is None or output.row_count != len(rows):
                    findings.append(
                        ValidationFinding(
                            "result.row_count_mismatch",
                            "candidate row count does not match its snapshot descriptor",
                        )
                    )

        report_payload = {
            "plan_id": result.plan_id,
            "input_sha256": result.input_snapshot.content_sha256,
            "output_sha256": result.output_snapshot.content_sha256 if result.output_snapshot else None,
            "findings": [
                {"code": finding.code, "message": finding.message, "severity": finding.severity.value}
                for finding in findings
            ],
        }
        encoded = json.dumps(report_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return ResultValidationReport(
            report_id=f"result-validation-{hashlib.sha256(encoded).hexdigest()[:24]}",
            plan_id=result.plan_id,
            input_sha256=result.input_snapshot.content_sha256,
            output_sha256=result.output_snapshot.content_sha256 if result.output_snapshot else None,
            findings=tuple(findings),
        )
