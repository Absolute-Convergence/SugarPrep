"""Deterministic validation of an unaccepted artifact-bundle draft."""

from __future__ import annotations

import hashlib
import json

from sugarprep.artifacts.bundle import ArtifactBundleDraft, calculate_draft_fingerprint
from sugarprep.artifacts.documents import PRODUCTION_ARTIFACT_FILENAMES
from sugarprep.artifacts.manifest import ArtifactState
from sugarprep.artifacts.schemas import ARTIFACT_SCHEMA_BY_NAME
from sugarprep.validation.reports import BundleValidationReport, ValidationFinding


class ArtifactBundleValidator:
    def validate(self, draft: ArtifactBundleDraft) -> BundleValidationReport:
        findings: list[ValidationFinding] = []
        expected_fingerprint = calculate_draft_fingerprint(
            recipe=draft.recipe,
            plan=draft.plan,
            profile=draft.profile,
            result=draft.result,
            result_validation_report_id=draft.result_validation_report_id,
            documents=draft.documents,
            manifest=draft.manifest,
        )
        if draft.draft_fingerprint != expected_fingerprint:
            findings.append(
                ValidationFinding("bundle.draft_fingerprint_mismatch", "draft contents no longer match identity")
            )
        if draft.result.output_snapshot is None:
            findings.append(ValidationFinding("bundle.output_missing", "draft has no candidate output"))
        if draft.manifest.plan_id != draft.plan.plan_id:
            findings.append(ValidationFinding("bundle.plan_mismatch", "manifest plan does not match draft plan"))
        if draft.manifest.profile_id != draft.profile.profile_id:
            findings.append(
                ValidationFinding("bundle.profile_mismatch", "manifest profile does not match draft profile")
            )
        if draft.manifest.result_validation_report_id != draft.result_validation_report_id:
            findings.append(
                ValidationFinding(
                    "bundle.result_report_mismatch",
                    "manifest result-validation evidence does not match the draft",
                )
            )
        if any(entry.state is not ArtifactState.CANDIDATE for entry in draft.manifest.entries):
            findings.append(
                ValidationFinding("bundle.invalid_state", "an unaccepted draft must contain only candidates")
            )

        entries = {entry.name: entry for entry in draft.manifest.entries}
        if set(entries) != set(PRODUCTION_ARTIFACT_FILENAMES):
            findings.append(
                ValidationFinding(
                    "bundle.artifact_set_invalid",
                    "draft does not contain the canonical production artifact set",
                )
            )
        for name, filename in PRODUCTION_ARTIFACT_FILENAMES.items():
            entry = entries.get(name)
            if entry is not None and entry.filename != filename:
                findings.append(
                    ValidationFinding(
                        "bundle.artifact_filename_invalid",
                        f"artifact {name} must use canonical filename {filename}",
                    )
                )
            schema = ARTIFACT_SCHEMA_BY_NAME[name]
            if entry is not None and entry.media_type != schema.media_type:
                findings.append(
                    ValidationFinding(
                        "bundle.artifact_media_type_invalid",
                        f"artifact {name} must use media type {schema.media_type}",
                    )
                )
            if entry is not None and schema.declares_content_digest != (entry.content_sha256 is not None):
                findings.append(
                    ValidationFinding(
                        "bundle.artifact_digest_policy_invalid",
                        f"artifact {name} does not follow its content-digest policy",
                    )
                )
        data_entry = entries.get("prepared_data")
        if data_entry is not None and data_entry.snapshot != draft.result.output_snapshot:
            findings.append(
                ValidationFinding("bundle.data_snapshot_mismatch", "data artifact is not the candidate output")
            )
        document_entries = {name: entry for name, entry in entries.items() if name not in {"prepared_data", "manifest"}}
        documents = {document.name: document for document in draft.documents}
        if set(documents) != set(document_entries):
            findings.append(
                ValidationFinding(
                    "bundle.document_set_invalid",
                    "serialized document set does not match the artifact manifest",
                )
            )
        for name, document in documents.items():
            entry = document_entries.get(name)
            if entry is not None and (
                entry.filename != document.filename
                or entry.media_type != document.media_type
                or entry.content_sha256 != document.content_sha256
            ):
                findings.append(
                    ValidationFinding(
                        "bundle.document_fingerprint_mismatch",
                        f"serialized document {name} does not match its manifest entry",
                    )
                )

        payload = {
            "draft_id": draft.draft_id,
            "draft_fingerprint": draft.draft_fingerprint,
            "findings": [
                {"code": finding.code, "message": finding.message, "severity": finding.severity.value}
                for finding in findings
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return BundleValidationReport(
            report_id=f"bundle-validation-{hashlib.sha256(encoded).hexdigest()[:24]}",
            draft_id=draft.draft_id,
            draft_fingerprint=draft.draft_fingerprint,
            findings=tuple(findings),
        )
