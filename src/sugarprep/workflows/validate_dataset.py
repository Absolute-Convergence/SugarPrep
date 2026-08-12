"""Validate-dataset application workflow."""

from __future__ import annotations

from sugarprep.domain import DatasetRef, DatasetSnapshot
from sugarprep.validation import DatasetValidationReport, DatasetValidator


class ValidateDatasetWorkflow:
    def __init__(self, validator: DatasetValidator) -> None:
        self._validator = validator

    def run(self, dataset: DatasetRef | DatasetSnapshot) -> DatasetValidationReport:
        if isinstance(dataset, DatasetSnapshot):
            return self._validator.validate_snapshot(dataset)
        return self._validator.validate(dataset)
