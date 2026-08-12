"""Validate explicit acceptance, commit durably, then create a bundle."""

from __future__ import annotations

import hashlib

from sugarprep.artifacts.bundle import AcceptanceDecision, ArtifactBundle, ArtifactBundleDraft
from sugarprep.artifacts.manifest import ArtifactState
from sugarprep.artifacts.serialization import serialize_manifest_document
from sugarprep.artifacts.store_port import ArtifactStore
from sugarprep.domain.errors import SugarPrepError
from sugarprep.validation.reports import BundleValidationReport


class ArtifactCommitError(SugarPrepError):
    pass


class ArtifactWriter:
    def __init__(self, store: ArtifactStore) -> None:
        self._store = store

    def commit(
        self,
        draft: ArtifactBundleDraft,
        bundle_report: BundleValidationReport,
        acceptance: AcceptanceDecision,
    ) -> ArtifactBundle:
        if not bundle_report.passed:
            raise ArtifactCommitError("cannot commit a draft with failing bundle validation")
        if (
            bundle_report.draft_id != draft.draft_id
            or bundle_report.draft_fingerprint != draft.draft_fingerprint
        ):
            raise ArtifactCommitError("bundle validation report does not match the current draft")
        if not acceptance.accepted:
            raise ArtifactCommitError("artifact draft was not accepted")
        if (
            acceptance.draft_id != draft.draft_id
            or acceptance.draft_fingerprint != draft.draft_fingerprint
            or acceptance.validation_report_id != bundle_report.report_id
        ):
            raise ArtifactCommitError("acceptance decision does not match the validated draft")

        bundle_key = ":".join(
            (
                draft.draft_id,
                draft.draft_fingerprint,
                bundle_report.report_id,
                acceptance.decision_id,
            )
        )
        bundle_id = f"bundle-{hashlib.sha256(bundle_key.encode('utf-8')).hexdigest()[:24]}"
        accepted_manifest = draft.manifest.with_state(ArtifactState.ACCEPTED)
        manifest_document = serialize_manifest_document(
            bundle_id=bundle_id,
            draft=draft,
            manifest=accepted_manifest,
            bundle_report=bundle_report,
            acceptance=acceptance,
        )
        receipt = self._store.commit(
            bundle_id=bundle_id,
            accepted_manifest=accepted_manifest,
            documents=(*draft.documents, manifest_document),
        )
        expected_entries = tuple(
            (entry.name, entry.filename, entry.content_sha256, ArtifactState.ACCEPTED)
            for entry in accepted_manifest.entries
        )
        receipt_entries = tuple(
            (entry.name, entry.filename, entry.content_sha256, entry.state)
            for entry in receipt.manifest.entries
        )
        if receipt_entries != expected_entries:
            raise ArtifactCommitError("artifact store receipt does not match the committed manifest")
        return ArtifactBundle(
            bundle_id=bundle_id,
            draft_id=draft.draft_id,
            draft_fingerprint=draft.draft_fingerprint,
            validation_report_id=bundle_report.report_id,
            acceptance_decision_id=acceptance.decision_id,
            manifest=receipt.manifest,
            bundle_locator=receipt.bundle_locator,
        )
