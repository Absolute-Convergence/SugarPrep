from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from sugarprep.domain import (
    CleanerExecutionEvidence,
    CleanerToolEvidence,
    DatasetProvenance,
    DatasetRef,
    DatasetSnapshot,
    DomainValidationError,
)


SHA_A = "a" * 64
SHA_B = "b" * 64


def test_dataset_snapshot_is_identity_not_a_tabular_facade() -> None:
    reference = DatasetRef(dataset_id="sales", storage_locator="source:active")
    snapshot = DatasetSnapshot(
        reference=reference,
        content_sha256=SHA_A.upper(),
        media_type="text/csv",
        headers=("date", "amount"),
        row_count=12,
        provenance=DatasetProvenance(operation="upload", parent_sha256=(SHA_B,)),
    )

    assert snapshot.content_sha256 == SHA_A
    assert snapshot.headers == ("date", "amount")
    assert not hasattr(snapshot, "iloc")
    assert not hasattr(snapshot, "groupby")
    with pytest.raises(FrozenInstanceError):
        snapshot.row_count = 13  # type: ignore[misc]


@pytest.mark.parametrize(
    ("headers", "row_count"),
    [(("value", "value"), 1), (("value",), -1)],
)
def test_dataset_snapshot_rejects_invalid_structure(headers: tuple[str, ...], row_count: int) -> None:
    with pytest.raises(DomainValidationError):
        DatasetSnapshot(
            reference=DatasetRef(dataset_id="sales", storage_locator="source:active"),
            content_sha256=SHA_A,
            media_type="text/csv",
            headers=headers,
            row_count=row_count,
        )


def test_cleaner_evidence_requires_exact_quarantine_total_and_source_parent() -> None:
    tool = CleanerToolEvidence(
        call_id="clean-001",
        tool_name="repair_ragged_rows",
        arguments={"pad_short_rows": True},
        rows_input=2,
        rows_output=1,
        rows_quarantined=1,
    )

    with pytest.raises(DomainValidationError, match="evidence total"):
        CleanerExecutionEvidence(
            evidence_id="cleaner-evidence",
            plan_candidate_id="cleaner-candidate",
            provider_id="qwen-cleaner",
            plan_id="cleaner-plan",
            input_sha256=SHA_A,
            output_sha256=SHA_B,
            tool_executions=(tool,),
            rows_quarantined=0,
            validation_passed=True,
        )

    evidence = CleanerExecutionEvidence(
        evidence_id="cleaner-evidence",
        plan_candidate_id="cleaner-candidate",
        provider_id="qwen-cleaner",
        plan_id="cleaner-plan",
        input_sha256=SHA_A,
        output_sha256=SHA_B,
        tool_executions=(tool,),
        rows_quarantined=1,
        validation_passed=True,
    )
    with pytest.raises(DomainValidationError, match="must be a provenance parent"):
        DatasetProvenance(
            operation="clean:cleaner-plan",
            parent_sha256=(SHA_B,),
            cleaner_evidence=evidence,
        )
