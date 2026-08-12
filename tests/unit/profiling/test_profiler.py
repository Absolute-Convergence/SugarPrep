from __future__ import annotations

from collections.abc import Iterable

from sugarprep.domain import DatasetRef, DatasetSnapshot
from sugarprep.profiling import DatasetProfiler


class FakeProfilingInput:
    def __init__(self, rows: tuple[tuple[str, ...], ...]) -> None:
        self.rows = rows
        self.asserted = False

    def inspect(self, reference: DatasetRef) -> DatasetSnapshot:
        return DatasetSnapshot(
            reference=reference,
            content_sha256="a" * 64,
            media_type="text/csv",
            headers=("date", "amount"),
            row_count=len(self.rows),
        )

    def iter_rows(self, snapshot: DatasetSnapshot) -> Iterable[tuple[str, ...]]:
        assert snapshot.reference.storage_locator == "opaque-token"
        return iter(self.rows)

    def assert_unchanged(self, snapshot: DatasetSnapshot) -> None:
        assert snapshot.content_sha256 == "a" * 64
        self.asserted = True


def test_profiler_uses_port_and_returns_domain_evidence() -> None:
    payload_input = FakeProfilingInput(
        (
            ("2026-01-01", "10"),
            ("2026-01-02", ""),
            ("", ""),
        )
    )
    profile = DatasetProfiler(payload_input).profile(
        DatasetRef(dataset_id="sales", storage_locator="opaque-token")
    )

    assert payload_input.asserted
    assert profile.profiled_row_count == 2
    assert profile.blank_row_count == 1
    assert profile.columns[0].date_like_count == 2
    assert profile.columns[1].numeric_success_count == 1
    assert profile.columns[1].missing_count == 1


def test_adaptive_profile_stops_without_changing_snapshot_identity() -> None:
    rows = tuple((str(index), str(index)) for index in range(10))
    payload_input = FakeProfilingInput(rows)
    from sugarprep.profiling import AdaptiveProfilePolicy

    profile = DatasetProfiler(payload_input).profile(
        DatasetRef(dataset_id="sales", storage_locator="opaque-token"),
        adaptive=True,
        adaptive_policy=AdaptiveProfilePolicy(min_rows=2, batch_size=2, stability_batches=2, max_rows=10),
    )

    assert profile.mode == "adaptive"
    assert profile.stop_reason == "adaptive_stable"
    assert profile.profiled_row_count < profile.snapshot.row_count
