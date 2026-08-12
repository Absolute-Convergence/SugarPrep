"""Thin ``sugarprep prepare`` command and explicit acceptance composition."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from sugarprep.artifacts import ArtifactAssembler, ArtifactWriter, create_acceptance_decision
from sugarprep.domain import DatasetRef
from sugarprep.infrastructure import (
    CsvProfilingPayloadInput,
    CsvTransformCandidateOutput,
    CsvTransformPayloadInput,
    CsvValidationPayloadInput,
    LocalArtifactStore,
)
from sugarprep.planning import compile_recipe, parse_recipe
from sugarprep.profiling import DatasetProfiler
from sugarprep.transforms import TransformPipeline
from sugarprep.validation import ArtifactBundleValidator, ResultValidator
from sugarprep.workflows import PrepareDatasetWorkflow


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("dataset", type=Path, help="Source CSV dataset")
    parser.add_argument("--recipe", type=Path, required=True, help="Explicit preparation recipe YAML")
    parser.add_argument("--output-root", type=Path, required=True, help="Owned candidate and bundle root")
    parser.add_argument("--dataset-id", help="Logical dataset identity; defaults to the filename stem")
    parser.add_argument(
        "--accept-by",
        help="Explicitly accept the validated draft under this actor identity and commit a bundle",
    )
    parser.set_defaults(command_handler=run)


def run(args: argparse.Namespace) -> int:
    reference = DatasetRef(
        dataset_id=args.dataset_id or args.dataset.stem,
        storage_locator=str(args.dataset),
    )
    profile = DatasetProfiler(CsvProfilingPayloadInput()).profile(reference)
    recipe = parse_recipe(args.recipe.read_text(encoding="utf-8"))
    plan = compile_recipe(recipe, profile)
    workflow = PrepareDatasetWorkflow(
        pipeline=TransformPipeline(
            CsvTransformPayloadInput(),
            CsvTransformCandidateOutput(args.output_root / "candidates"),
        ),
        result_validator=ResultValidator(CsvValidationPayloadInput()),
        assembler=ArtifactAssembler(),
        bundle_validator=ArtifactBundleValidator(),
        writer=ArtifactWriter(LocalArtifactStore(args.output_root / "bundles")),
    )
    review = workflow.prepare(recipe=recipe, plan=plan, profile=profile)
    payload: dict[str, object] = {
        "plan_id": plan.plan_id,
        "result_validation_report_id": review.result_report.report_id,
        "result_validation_passed": review.result_report.passed,
        "output_sha256": (
            review.result.output_snapshot.content_sha256 if review.result.output_snapshot else None
        ),
        "reject_count": len(review.result.rejected_rows),
        "warning_count": len(review.result.warnings),
    }
    if not review.ready_for_acceptance or review.draft is None or review.bundle_report is None:
        payload["status"] = "validation_failed"
        payload["findings"] = [
            {"code": finding.code, "message": finding.message, "severity": finding.severity.value}
            for finding in review.result_report.findings
        ]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1

    payload.update(
        {
            "draft_id": review.draft.draft_id,
            "draft_fingerprint": review.draft.draft_fingerprint,
            "bundle_validation_report_id": review.bundle_report.report_id,
            "bundle_validation_passed": review.bundle_report.passed,
        }
    )
    if args.accept_by is None:
        payload["status"] = "ready_for_acceptance"
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    decision = create_acceptance_decision(
        review.draft,
        validation_report_id=review.bundle_report.report_id,
        accepted_by=args.accept_by,
        decided_at=datetime.now(timezone.utc),
    )
    bundle = workflow.accept(review, decision)
    payload.update(
        {
            "status": "accepted",
            "acceptance_decision_id": decision.decision_id,
            "bundle_id": bundle.bundle_id,
        }
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
