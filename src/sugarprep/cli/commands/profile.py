"""Thin ``sugarprep profile`` command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sugarprep.domain import DatasetRef
from sugarprep.infrastructure import CsvProfilingPayloadInput
from sugarprep.profiling import DatasetProfiler
from sugarprep.workflows import ProfileDatasetWorkflow


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("dataset", type=Path, help="CSV dataset to profile")
    parser.add_argument("--dataset-id", help="Logical dataset identity; defaults to the filename stem")
    parser.set_defaults(command_handler=run)


def run(args: argparse.Namespace) -> int:
    reference = DatasetRef(
        dataset_id=args.dataset_id or args.dataset.stem,
        storage_locator=str(args.dataset),
    )
    profile = ProfileDatasetWorkflow(DatasetProfiler(CsvProfilingPayloadInput())).run(reference)
    payload = {
        "profile_id": profile.profile_id,
        "dataset_id": profile.snapshot.reference.dataset_id,
        "content_sha256": profile.snapshot.content_sha256,
        "headers": list(profile.snapshot.headers),
        "row_count": profile.snapshot.row_count,
        "profiled_row_count": profile.profiled_row_count,
        "blank_row_count": profile.blank_row_count,
        "mode": profile.mode,
        "stop_reason": profile.stop_reason,
        "columns": [
            {
                "name": column.name,
                "missing_count": column.missing_count,
                "numeric_value_candidate": column.numeric_value_candidate,
                "likely_integer": column.likely_integer,
                "likely_date_axis": column.likely_date_axis,
            }
            for column in profile.columns
        ],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
