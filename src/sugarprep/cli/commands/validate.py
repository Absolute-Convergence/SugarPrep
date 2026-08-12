"""Thin ``sugarprep validate`` command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sugarprep.domain import DatasetRef
from sugarprep.infrastructure import CsvValidationPayloadInput
from sugarprep.validation import DatasetValidator
from sugarprep.workflows import ValidateDatasetWorkflow


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("dataset", type=Path, help="CSV dataset to validate")
    parser.add_argument("--dataset-id", help="Logical dataset identity; defaults to the filename stem")
    parser.set_defaults(command_handler=run)


def run(args: argparse.Namespace) -> int:
    reference = DatasetRef(
        dataset_id=args.dataset_id or args.dataset.stem,
        storage_locator=str(args.dataset),
    )
    report = ValidateDatasetWorkflow(DatasetValidator(CsvValidationPayloadInput())).run(reference)
    payload = {
        "report_id": report.report_id,
        "passed": report.passed,
        "dataset_id": report.snapshot.reference.dataset_id,
        "content_sha256": report.snapshot.content_sha256,
        "headers": list(report.snapshot.headers),
        "row_count": report.snapshot.row_count,
        "findings": [
            {"code": finding.code, "message": finding.message, "severity": finding.severity.value}
            for finding in report.findings
        ],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report.passed else 1
