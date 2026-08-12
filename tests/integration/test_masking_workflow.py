from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from sugarprep.artifacts import ArtifactAssembler, ArtifactWriter, create_acceptance_decision
from sugarprep.domain import DatasetRef, Layout, OutputColumn, Recipe, TransformSpec
from sugarprep.infrastructure import (
    CsvMaskingCandidateOutput,
    CsvMaskingPayloadInput,
    CsvProfilingPayloadInput,
    CsvTransformCandidateOutput,
    CsvTransformPayloadInput,
    CsvValidationPayloadInput,
    LocalArtifactStore,
)
from sugarprep.infrastructure.filesystem import resolve_local_file
from sugarprep.inference import PiiInferenceService, PiiSpanCandidate
from sugarprep.planning import compile_recipe
from sugarprep.profiling import DatasetProfiler
from sugarprep.transforms import MaskingPipeline, TransformPipeline, detect_pii
from sugarprep.validation import ArtifactBundleValidator, DatasetValidator, ResultValidator
from sugarprep.workflows import (
    MaskDatasetWorkflow,
    PrepareDatasetWorkflow,
    ProfileDatasetWorkflow,
    ValidateDatasetWorkflow,
)


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "sensitive.csv"
    source.write_text(
        "Date,Value,Contact\n"
        "20260809,10,ada@example.com\n"
        '20260810,11,"Call 312-555-0199 token=abc123"\n',
        encoding="utf-8",
    )
    return source


def _mask(tmp_path: Path):
    source = _source(tmp_path)
    payload = CsvMaskingPayloadInput()
    snapshot = payload.inspect(DatasetRef(dataset_id="sensitive", storage_locator=source.as_uri()))
    result = MaskDatasetWorkflow(
        MaskingPipeline(payload, CsvMaskingCandidateOutput(tmp_path / "masked-candidates"))
    ).run(snapshot)
    return source, result


def test_deterministic_masking_preserves_source_and_binds_evidence(tmp_path: Path) -> None:
    source, result = _mask(tmp_path)

    assert "ada@example.com" in source.read_text(encoding="utf-8")
    masked_path = resolve_local_file(result.output_snapshot.reference)
    masked_text = masked_path.read_text(encoding="utf-8")
    assert "ada@example.com" not in masked_text
    assert "312-555-0199" not in masked_text
    assert "token=abc123" not in masked_text
    assert "[masked email]" in masked_text
    assert "[masked phone] [masked token]" in masked_text
    assert detect_pii(masked_text) == ()
    assert result.evidence.row_count == 2
    assert result.evidence.cell_count == 6
    assert result.evidence.masked_cell_count == 2
    assert {item.kind: item.count for item in result.evidence.findings} == {
        "email": 1,
        "phone": 1,
        "token": 1,
    }
    assert result.output_snapshot.provenance.parent_sha256 == (result.input_snapshot.content_sha256,)
    assert result.output_snapshot.provenance.masking_evidence == result.evidence
    validation = ValidateDatasetWorkflow(DatasetValidator(CsvValidationPayloadInput())).run(
        result.output_snapshot
    )
    assert validation.passed
    assert validation.snapshot.provenance.masking_evidence == result.evidence


class NameSpanProvider:
    provider_id = "pii-ner-test"

    def detect(self, text: str) -> tuple[PiiSpanCandidate, ...]:
        name = "Ada Lovelace"
        start = text.find(name)
        if start < 0:
            return ()
        return (PiiSpanCandidate(start=start, end=start + len(name), kind="first_name", score=0.99),)


def test_model_backed_masking_combines_ner_and_deterministic_spans(tmp_path: Path) -> None:
    source = tmp_path / "model-sensitive.csv"
    source.write_text(
        "Name,Contact\nAda Lovelace,ada@example.com\n",
        encoding="utf-8",
    )
    payload = CsvMaskingPayloadInput()
    snapshot = payload.inspect(DatasetRef(dataset_id="model-sensitive", storage_locator=source.as_uri()))
    result = MaskDatasetWorkflow(
        MaskingPipeline(
            payload,
            CsvMaskingCandidateOutput(tmp_path / "model-masked-candidates"),
            PiiInferenceService(NameSpanProvider()),
        )
    ).run(snapshot)

    assert "Ada Lovelace" in source.read_text(encoding="utf-8")
    masked = resolve_local_file(result.output_snapshot.reference).read_text(encoding="utf-8")
    assert "Ada Lovelace" not in masked
    assert "ada@example.com" not in masked
    assert "[masked first_name]" in masked
    assert "[masked email]" in masked
    assert result.evidence.model_provider_id == "pii-ner-test"
    assert result.evidence.model_detection_count == 1
    assert result.evidence.deterministic_detection_count == 1
    assert result.evidence.algorithm == "pii_ner_plus_deterministic_regex_v1"


def test_masking_evidence_reaches_the_accepted_bundle_without_paths(tmp_path: Path) -> None:
    source, masking = _mask(tmp_path)
    profile = ProfileDatasetWorkflow(DatasetProfiler(CsvProfilingPayloadInput())).run(
        masking.output_snapshot
    )
    recipe = Recipe(
        version=1,
        name="masked_values",
        output_columns=(
            OutputColumn(name="date", source="Date", transforms=(TransformSpec("trim"),)),
            OutputColumn(name="value", source="Value", transforms=(TransformSpec("parse_numeric"),)),
        ),
        layout=Layout(
            time_column="date",
            time_kind="YyyyMmDd",
            value_columns=("value",),
            primary_value_column="value",
        ),
    )
    plan = compile_recipe(recipe, profile)
    workflow = PrepareDatasetWorkflow(
        pipeline=TransformPipeline(
            CsvTransformPayloadInput(),
            CsvTransformCandidateOutput(tmp_path / "prepared-candidates"),
        ),
        result_validator=ResultValidator(CsvValidationPayloadInput()),
        assembler=ArtifactAssembler(),
        bundle_validator=ArtifactBundleValidator(),
        writer=ArtifactWriter(LocalArtifactStore(tmp_path / "bundles")),
    )
    review = workflow.prepare(recipe=recipe, plan=plan, profile=profile)
    assert review.draft is not None and review.bundle_report is not None
    decision = create_acceptance_decision(
        review.draft,
        validation_report_id=review.bundle_report.report_id,
        accepted_by="masking-integration-test",
        decided_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )
    bundle = workflow.accept(review, decision)
    data_entry = next(entry for entry in bundle.manifest.entries if entry.name == "prepared_data")
    assert data_entry.snapshot is not None
    bundle_root = resolve_local_file(data_entry.snapshot.reference).parent

    manifest = json.loads((bundle_root / "manifest.json").read_text(encoding="utf-8"))
    serialized_profile = json.loads((bundle_root / "profile.json").read_text(encoding="utf-8"))
    serialized_plan = json.loads((bundle_root / "compiled-plan.json").read_text(encoding="utf-8"))
    expected_id = masking.evidence.evidence_id
    assert manifest["masking_evidence"]["evidence_id"] == expected_id
    assert serialized_profile["provenance"]["masking_evidence"]["evidence_id"] == expected_id
    assert serialized_plan["input"]["provenance"]["masking_evidence"]["evidence_id"] == expected_id
    serialized = b"\n".join(path.read_bytes() for path in bundle_root.iterdir())
    assert source.as_uri().encode("utf-8") not in serialized
    assert str(tmp_path).encode("utf-8") not in serialized
