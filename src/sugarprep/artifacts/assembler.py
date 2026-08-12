"""Assemble a validated preparation result into an unaccepted draft."""

from __future__ import annotations

from sugarprep.artifacts.bundle import ArtifactBundleDraft, calculate_draft_fingerprint
from sugarprep.artifacts.documents import PRODUCTION_ARTIFACT_FILENAMES
from sugarprep.artifacts.manifest import ArtifactEntry, ArtifactManifest
from sugarprep.artifacts.serialization import serialize_draft_documents
from sugarprep.domain.errors import SugarPrepError
from sugarprep.domain.plan import PreparationPlan
from sugarprep.domain.profile import DatasetProfile
from sugarprep.domain.recipe import Recipe
from sugarprep.domain.result import PreparationResult
from sugarprep.validation.reports import ResultValidationReport


class ArtifactAssemblyError(SugarPrepError):
    pass


class ArtifactAssembler:
    def assemble(
        self,
        *,
        result: PreparationResult,
        result_report: ResultValidationReport,
        recipe: Recipe,
        plan: PreparationPlan,
        profile: DatasetProfile,
    ) -> ArtifactBundleDraft:
        if not result_report.passed:
            raise ArtifactAssemblyError("cannot assemble a draft from a failing result validation report")
        if result.output_snapshot is None:
            raise ArtifactAssemblyError("cannot assemble a draft without candidate output")
        if result_report.plan_id != result.plan_id or result_report.plan_id != plan.plan_id:
            raise ArtifactAssemblyError("result validation report does not match the plan")
        if result_report.input_sha256 != result.input_snapshot.content_sha256:
            raise ArtifactAssemblyError("result validation report does not match the input snapshot")
        if result_report.output_sha256 != result.output_snapshot.content_sha256:
            raise ArtifactAssemblyError("result validation report does not match the output snapshot")
        if plan.input_snapshot != result.input_snapshot or profile.snapshot != result.input_snapshot:
            raise ArtifactAssemblyError("plan, profile, and result do not bind the same input snapshot")
        if recipe.name != plan.recipe_name or recipe.version != plan.version:
            raise ArtifactAssemblyError("recipe does not match the compiled plan")

        documents = serialize_draft_documents(
            recipe=recipe,
            plan=plan,
            profile=profile,
            result=result,
        )
        entries = [
            ArtifactEntry(
                name="prepared_data",
                filename=PRODUCTION_ARTIFACT_FILENAMES["prepared_data"],
                media_type=result.output_snapshot.media_type,
                content_sha256=result.output_snapshot.content_sha256,
                snapshot=result.output_snapshot,
            )
        ]
        entries.extend(
            ArtifactEntry(
                name=document.name,
                filename=document.filename,
                media_type=document.media_type,
                content_sha256=document.content_sha256,
            )
            for document in documents
        )
        entries.append(
            ArtifactEntry(
                name="manifest",
                filename=PRODUCTION_ARTIFACT_FILENAMES["manifest"],
                media_type="application/json",
                content_sha256=None,
            )
        )
        manifest = ArtifactManifest(
            schema_version=1,
            plan_id=plan.plan_id,
            recipe_name=recipe.name,
            profile_id=profile.profile_id,
            result_validation_report_id=result_report.report_id,
            entries=tuple(entries),
        )
        fingerprint = calculate_draft_fingerprint(
            recipe=recipe,
            plan=plan,
            profile=profile,
            result=result,
            result_validation_report_id=result_report.report_id,
            documents=documents,
            manifest=manifest,
        )
        return ArtifactBundleDraft(
            draft_id=f"draft-{fingerprint[:24]}",
            draft_fingerprint=fingerprint,
            recipe=recipe,
            plan=plan,
            profile=profile,
            result=result,
            result_validation_report=result_report,
            documents=documents,
            manifest=manifest,
        )
