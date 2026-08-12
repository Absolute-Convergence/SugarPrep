from __future__ import annotations

import pytest

from sugarprep.domain import ColumnProfile, DatasetProfile, DatasetRef, DatasetSnapshot, DomainValidationError


def _snapshot() -> DatasetSnapshot:
    return DatasetSnapshot(
        reference=DatasetRef(dataset_id="sales", storage_locator="source:active"),
        content_sha256="a" * 64,
        media_type="text/csv",
        headers=("date", "amount"),
        row_count=10,
    )


def test_profile_is_evidence_for_one_snapshot() -> None:
    profile = DatasetProfile(
        profile_id="profile-1",
        snapshot=_snapshot(),
        columns=(
            ColumnProfile(name="date", row_count=10, missing_count=0, date_like_count=10),
            ColumnProfile(name="amount", row_count=10, missing_count=1, numeric_success_count=9),
        ),
        profiled_row_count=10,
    )

    assert profile.columns[1].non_missing_count == 9
    assert not hasattr(profile, "pii_candidates")


def test_profile_column_order_must_match_snapshot() -> None:
    with pytest.raises(DomainValidationError, match="header order"):
        DatasetProfile(
            profile_id="profile-1",
            snapshot=_snapshot(),
            columns=(
                ColumnProfile(name="amount", row_count=10, missing_count=0),
                ColumnProfile(name="date", row_count=10, missing_count=0),
            ),
            profiled_row_count=10,
        )
