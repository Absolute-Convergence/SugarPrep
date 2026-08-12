"""Application sequence from deterministic execution through explicit acceptance."""

from __future__ import annotations

from dataclasses import dataclass

from sugarprep.artifacts import (
    AcceptanceDecision,
    ArtifactAssembler,
    ArtifactBundle,
    ArtifactBundleDraft,
    ArtifactWriter,
)
from sugarprep.domain import DatasetProfile, PreparationPlan, PreparationResult, Recipe
from sugarprep.transforms import TransformPipeline
from sugarprep.validation import (
    ArtifactBundleValidator,
    BundleValidationReport,
    ResultValidationReport,
    ResultValidator,
)


@dataclass(frozen=True, slots=True)
class PreparationReview:
    result: PreparationResult
    result_report: ResultValidationReport
    draft: ArtifactBundleDraft | None = None
    bundle_report: BundleValidationReport | None = None

    @property
    def ready_for_acceptance(self) -> bool:
        return (
            self.result_report.passed
            and self.draft is not None
            and self.bundle_report is not None
            and self.bundle_report.passed
        )


class PrepareDatasetWorkflow:
    """Orchestrate the exact result-to-draft validation sequence."""

    def __init__(
        self,
        *,
        pipeline: TransformPipeline,
        result_validator: ResultValidator,
        assembler: ArtifactAssembler,
        bundle_validator: ArtifactBundleValidator,
        writer: ArtifactWriter,
    ) -> None:
        self._pipeline = pipeline
        self._result_validator = result_validator
        self._assembler = assembler
        self._bundle_validator = bundle_validator
        self._writer = writer

    def prepare(
        self,
        *,
        recipe: Recipe,
        plan: PreparationPlan,
        profile: DatasetProfile,
    ) -> PreparationReview:
        result = self._pipeline.execute(plan)
        result_report = self._result_validator.validate(result, plan)
        if not result_report.passed:
            return PreparationReview(result=result, result_report=result_report)

        draft = self._assembler.assemble(
            result=result,
            result_report=result_report,
            recipe=recipe,
            plan=plan,
            profile=profile,
        )
        bundle_report = self._bundle_validator.validate(draft)
        return PreparationReview(
            result=result,
            result_report=result_report,
            draft=draft,
            bundle_report=bundle_report,
        )

    def accept(self, review: PreparationReview, decision: AcceptanceDecision) -> ArtifactBundle:
        if not review.ready_for_acceptance or review.draft is None or review.bundle_report is None:
            raise ValueError("preparation review is not ready for acceptance")
        return self._writer.commit(review.draft, review.bundle_report, decision)
