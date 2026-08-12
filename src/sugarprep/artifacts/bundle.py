"""Sole definitions of draft, acceptance, and finalized bundle values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import TYPE_CHECKING

from sugarprep.artifacts.documents import ArtifactDocument
from sugarprep.artifacts.manifest import ArtifactManifest, ArtifactState
from sugarprep.domain.errors import DomainValidationError
from sugarprep.domain.plan import PreparationPlan
from sugarprep.domain.profile import DatasetProfile
from sugarprep.domain.recipe import Recipe
from sugarprep.domain.result import PreparationResult

if TYPE_CHECKING:
    from sugarprep.validation.reports import ResultValidationReport


@dataclass(frozen=True, slots=True)
class ArtifactBundleDraft:
    draft_id: str
    draft_fingerprint: str
    recipe: Recipe
    plan: PreparationPlan
    profile: DatasetProfile
    result: PreparationResult
    result_validation_report: ResultValidationReport
    documents: tuple[ArtifactDocument, ...]
    manifest: ArtifactManifest

    def __post_init__(self) -> None:
        for field_name in ("draft_id", "draft_fingerprint"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"artifact draft {field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())
        if not all(
            hasattr(self.result_validation_report, field_name)
            for field_name in ("report_id", "plan_id", "input_sha256", "output_sha256", "findings", "passed")
        ):
            raise DomainValidationError("artifact draft result validation must be a report")
        documents = tuple(self.documents)
        if not documents or not all(isinstance(item, ArtifactDocument) for item in documents):
            raise DomainValidationError("artifact draft requires serialized artifact documents")
        if len({item.name for item in documents}) != len(documents):
            raise DomainValidationError("artifact draft document names must be unique")
        object.__setattr__(self, "documents", documents)
        if not all(entry.state is ArtifactState.CANDIDATE for entry in self.manifest.entries):
            raise DomainValidationError("artifact draft manifest entries must be candidate state")
        expected = calculate_draft_fingerprint(
            recipe=self.recipe,
            plan=self.plan,
            profile=self.profile,
            result=self.result,
            result_validation_report_id=self.result_validation_report.report_id,
            documents=self.documents,
            manifest=self.manifest,
        )
        if self.draft_fingerprint != expected or self.draft_id != f"draft-{expected[:24]}":
            raise DomainValidationError("artifact draft identity does not match its exact contents")

    @property
    def result_validation_report_id(self) -> str:
        return self.result_validation_report.report_id


@dataclass(frozen=True, slots=True)
class AcceptanceDecision:
    decision_id: str
    draft_id: str
    draft_fingerprint: str
    validation_report_id: str
    accepted: bool
    accepted_by: str
    decided_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "decision_id",
            "draft_id",
            "draft_fingerprint",
            "validation_report_id",
            "accepted_by",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"acceptance decision {field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())
        if not isinstance(self.accepted, bool):
            raise DomainValidationError("accepted must be boolean")
        if not isinstance(self.decided_at, datetime) or self.decided_at.tzinfo is None:
            raise DomainValidationError("decided_at must be a timezone-aware datetime")


@dataclass(frozen=True, slots=True)
class ArtifactBundle:
    bundle_id: str
    draft_id: str
    draft_fingerprint: str
    validation_report_id: str
    acceptance_decision_id: str
    manifest: ArtifactManifest
    bundle_locator: str

    def __post_init__(self) -> None:
        for field_name in (
            "bundle_id",
            "draft_id",
            "draft_fingerprint",
            "validation_report_id",
            "acceptance_decision_id",
            "bundle_locator",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"artifact bundle {field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())
        if not all(entry.state is ArtifactState.ACCEPTED for entry in self.manifest.entries):
            raise DomainValidationError("final artifact bundle entries must be accepted")


def calculate_draft_fingerprint(
    *,
    recipe: Recipe,
    plan: PreparationPlan,
    profile: DatasetProfile,
    result: PreparationResult,
    result_validation_report_id: str,
    documents: tuple[ArtifactDocument, ...],
    manifest: ArtifactManifest,
) -> str:
    payload = {
        "recipe": {"name": recipe.name, "version": recipe.version},
        "plan_id": plan.plan_id,
        "profile_id": profile.profile_id,
        "input_sha256": result.input_snapshot.content_sha256,
        "output_sha256": result.output_snapshot.content_sha256 if result.output_snapshot else None,
        "result_validation_report_id": result_validation_report_id,
        "documents": [
            {
                "name": document.name,
                "filename": document.filename,
                "media_type": document.media_type,
                "content_sha256": document.content_sha256,
            }
            for document in documents
        ],
        "manifest": {
            "schema_version": manifest.schema_version,
            "plan_id": manifest.plan_id,
            "recipe_name": manifest.recipe_name,
            "profile_id": manifest.profile_id,
            "result_validation_report_id": manifest.result_validation_report_id,
            "entries": [
                {
                    "name": entry.name,
                    "filename": entry.filename,
                    "sha256": entry.content_sha256,
                    "media_type": entry.media_type,
                    "state": entry.state.value,
                }
                for entry in manifest.entries
            ],
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_acceptance_decision(
    draft: ArtifactBundleDraft,
    *,
    validation_report_id: str,
    accepted_by: str,
    decided_at: datetime,
    accepted: bool = True,
) -> AcceptanceDecision:
    payload = {
        "draft_id": draft.draft_id,
        "draft_fingerprint": draft.draft_fingerprint,
        "validation_report_id": validation_report_id,
        "accepted": accepted,
        "accepted_by": accepted_by,
        "decided_at": decided_at.isoformat(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return AcceptanceDecision(
        decision_id=f"acceptance-{hashlib.sha256(encoded).hexdigest()[:24]}",
        draft_id=draft.draft_id,
        draft_fingerprint=draft.draft_fingerprint,
        validation_report_id=validation_report_id,
        accepted=accepted,
        accepted_by=accepted_by,
        decided_at=decided_at,
    )
