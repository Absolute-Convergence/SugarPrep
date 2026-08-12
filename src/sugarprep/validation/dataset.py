"""Deterministic structural validation for a referenced dataset."""

from __future__ import annotations

import hashlib
import json

from sugarprep.domain.dataset import DatasetRef, DatasetSnapshot
from sugarprep.validation.payload_input import ValidationPayloadInput
from sugarprep.validation.reports import DatasetValidationReport, ValidationFinding


class DatasetValidator:
    def __init__(self, payload_input: ValidationPayloadInput) -> None:
        self._payload_input = payload_input

    def validate(self, reference: DatasetRef) -> DatasetValidationReport:
        snapshot = self._payload_input.inspect(reference)
        return self.validate_snapshot(snapshot)

    def validate_snapshot(self, snapshot: DatasetSnapshot) -> DatasetValidationReport:
        """Validate an existing snapshot without discarding provenance evidence."""

        findings: list[ValidationFinding] = []
        self._payload_input.assert_unchanged(snapshot)
        rows = tuple(self._payload_input.iter_rows(snapshot))
        if not snapshot.headers:
            findings.append(ValidationFinding("dataset.headers_missing", "dataset has no headers"))
        if any(len(row) != len(snapshot.headers) for row in rows):
            findings.append(ValidationFinding("dataset.row_shape_mismatch", "dataset contains a malformed row"))
        if snapshot.row_count is None or snapshot.row_count != len(rows):
            findings.append(
                ValidationFinding(
                    "dataset.row_count_mismatch",
                    "dataset row count does not match its inspected snapshot",
                )
            )
        payload = {
            "dataset_id": snapshot.reference.dataset_id,
            "sha256": snapshot.content_sha256,
            "findings": [
                {"code": finding.code, "message": finding.message, "severity": finding.severity.value}
                for finding in findings
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return DatasetValidationReport(
            report_id=f"dataset-validation-{hashlib.sha256(encoded).hexdigest()[:24]}",
            snapshot=snapshot,
            findings=tuple(findings),
        )
