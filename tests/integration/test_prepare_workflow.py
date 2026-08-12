from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
import json

import pytest

from sugarprep.artifacts import (
    ArtifactAssembler,
    ArtifactCommitError,
    ArtifactDocument,
    ArtifactState,
    ArtifactWriter,
    create_acceptance_decision,
)
from sugarprep.domain import DatasetRef
from sugarprep.infrastructure import (
    CsvProfilingPayloadInput,
    CsvTransformCandidateOutput,
    CsvTransformPayloadInput,
    CsvValidationPayloadInput,
    LocalArtifactStore,
    LocalArtifactStoreError,
)
from sugarprep.infrastructure.filesystem import resolve_local_file
from sugarprep.planning import compile_recipe, parse_recipe
from sugarprep.profiling import DatasetProfiler
from sugarprep.transforms import TransformPipeline
from sugarprep.validation import ArtifactBundleValidator, ResultValidator, validate_sugarbot_package
from sugarprep.workflows import PrepareDatasetWorkflow


def _workflow(tmp_path: Path) -> PrepareDatasetWorkflow:
    return PrepareDatasetWorkflow(
        pipeline=TransformPipeline(
            CsvTransformPayloadInput(),
            CsvTransformCandidateOutput(tmp_path / "candidates"),
        ),
        result_validator=ResultValidator(CsvValidationPayloadInput()),
        assembler=ArtifactAssembler(),
        bundle_validator=ArtifactBundleValidator(),
        writer=ArtifactWriter(LocalArtifactStore(tmp_path / "bundles")),
    )


def _inputs(tmp_path: Path, volume: str = "1.2K"):
    source = tmp_path / "ohlcv.csv"
    source.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        f"20260808,$10.00,$12.00,$9.00,$11.00,{volume}\n",
        encoding="utf-8",
    )
    profile = DatasetProfiler(CsvProfilingPayloadInput()).profile(
        DatasetRef(dataset_id="quickstart", storage_locator=source.as_uri())
    )
    recipe = parse_recipe(Path("examples/quickstart/recipe.yaml").read_text(encoding="utf-8"))
    return source, recipe, profile, compile_recipe(recipe, profile)


def test_exact_result_validation_draft_validation_acceptance_commit_sequence(tmp_path: Path) -> None:
    source, recipe, profile, plan = _inputs(tmp_path)
    workflow = _workflow(tmp_path)

    review = workflow.prepare(recipe=recipe, plan=plan, profile=profile)

    assert review.ready_for_acceptance
    assert review.draft is not None
    assert review.bundle_report is not None
    assert review.draft.manifest.entries[0].state.value == "candidate"
    assert not (tmp_path / "bundles").exists()

    decision = create_acceptance_decision(
        review.draft,
        validation_report_id=review.bundle_report.report_id,
        accepted_by="integration-test",
        decided_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )
    bundle = workflow.accept(review, decision)

    assert bundle.manifest.entries[0].state.value == "accepted"
    committed_data = resolve_local_file(bundle.manifest.entries[0].snapshot.reference)
    assert committed_data.is_file()
    assert committed_data.read_text(encoding="utf-8").startswith("date,open,high,low,close,volume")
    assert source.read_text(encoding="utf-8").startswith("Date,Open,High,Low,Close,Volume")
    bundle_root = committed_data.parent
    expected_files = {
        "data.csv",
        "layout.json",
        "manifest.json",
        "profile.json",
        "compiled-plan.json",
        "warnings.json",
        "rejects.csv",
    }
    assert {path.name for path in bundle_root.iterdir()} == expected_files

    package_files = {name: (bundle_root / name).read_bytes() for name in expected_files}
    contract_report = validate_sugarbot_package(package_files)
    assert contract_report.passed, contract_report.findings

    layout = json.loads(package_files["layout.json"])
    manifest = json.loads(package_files["manifest.json"])
    assert "ingest" not in layout and "data_spec" not in layout
    assert layout["primary_value_col"] in layout["value_cols"]
    assert manifest["state"] == "accepted"
    assert manifest["validation"]["result"]["passed"]
    assert manifest["validation"]["bundle"]["passed"]
    assert manifest["validation"]["acceptance"]["decision_id"] == decision.decision_id
    serialized = b"\n".join(package_files.values())
    assert str(tmp_path).encode("utf-8") not in serialized
    assert source.as_uri().encode("utf-8") not in serialized


def test_failed_result_creates_no_draft_or_bundle(tmp_path: Path) -> None:
    _, recipe, profile, plan = _inputs(tmp_path, volume="-1")

    review = _workflow(tmp_path).prepare(recipe=recipe, plan=plan, profile=profile)

    assert not review.result_report.passed
    assert review.draft is None
    assert review.bundle_report is None
    assert not (tmp_path / "bundles").exists()
    assert list((tmp_path / "candidates").iterdir()) == []


def test_acceptance_must_name_the_exact_bundle_validation_report(tmp_path: Path) -> None:
    _, recipe, profile, plan = _inputs(tmp_path)
    workflow = _workflow(tmp_path)
    review = workflow.prepare(recipe=recipe, plan=plan, profile=profile)
    assert review.draft is not None

    mismatched = create_acceptance_decision(
        review.draft,
        validation_report_id="bundle-validation-wrong",
        accepted_by="integration-test",
        decided_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )

    with pytest.raises(ArtifactCommitError, match="does not match"):
        workflow.accept(review, mismatched)
    assert not (tmp_path / "bundles").exists()


def test_atomic_store_removes_staging_bundle_after_document_mismatch(tmp_path: Path) -> None:
    _, recipe, profile, plan = _inputs(tmp_path)
    review = _workflow(tmp_path).prepare(recipe=recipe, plan=plan, profile=profile)
    assert review.draft is not None

    documents = list(review.draft.documents)
    documents[0] = replace(documents[0], content=b"{}\n")
    documents.append(
        ArtifactDocument(
            name="manifest",
            filename="manifest.json",
            media_type="application/json",
            content=b"{}\n",
        )
    )
    store_root = tmp_path / "rollback-bundles"
    store = LocalArtifactStore(store_root)

    with pytest.raises(LocalArtifactStoreError, match="fingerprint mismatch"):
        store.commit(
            bundle_id="bundle-rollback-test",
            accepted_manifest=review.draft.manifest.with_state(ArtifactState.ACCEPTED),
            documents=tuple(documents),
        )

    assert not (store_root / "bundle-rollback-test").exists()
    assert list(store_root.iterdir()) == []
