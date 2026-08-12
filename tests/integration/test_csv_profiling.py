from __future__ import annotations

from pathlib import Path

import pytest

from sugarprep.domain import DatasetRef
from sugarprep.infrastructure import CsvPayloadError, CsvProfilingPayloadInput
from sugarprep.profiling import DatasetProfiler


def test_csv_infrastructure_profiles_without_exposing_paths_to_capability(tmp_path: Path) -> None:
    source = tmp_path / "sales.csv"
    source.write_text("date,amount\n2026-01-01,10\n2026-01-02,20\n", encoding="utf-8")
    reference = DatasetRef(dataset_id="sales", storage_locator=source.as_uri())

    profile = DatasetProfiler(CsvProfilingPayloadInput()).profile(reference)

    assert profile.snapshot.reference == reference
    assert profile.snapshot.headers == ("date", "amount")
    assert profile.snapshot.row_count == 2
    assert profile.columns[1].numeric_value_candidate


def test_csv_infrastructure_detects_snapshot_staleness(tmp_path: Path) -> None:
    source = tmp_path / "sales.csv"
    source.write_text("date,amount\n2026-01-01,10\n", encoding="utf-8")
    payload_input = CsvProfilingPayloadInput()
    snapshot = payload_input.inspect(DatasetRef(dataset_id="sales", storage_locator=str(source)))
    source.write_text("date,amount\n2026-01-01,11\n", encoding="utf-8")

    with pytest.raises(CsvPayloadError, match="changed"):
        payload_input.assert_unchanged(snapshot)
