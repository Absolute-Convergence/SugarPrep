"""Path-free canonical serializers for the SugarPrep production package."""

from __future__ import annotations

from collections.abc import Mapping
import csv
from dataclasses import asdict
from io import StringIO
import json
from typing import Any

from sugarprep.artifacts.bundle import AcceptanceDecision, ArtifactBundleDraft
from sugarprep.artifacts.documents import ArtifactDocument, PRODUCTION_ARTIFACT_FILENAMES
from sugarprep.artifacts.manifest import ArtifactManifest
from sugarprep.artifacts.schemas import ARTIFACT_SCHEMA_BY_NAME
from sugarprep.domain.plan import PreparationPlan
from sugarprep.domain.profile import DatasetProfile
from sugarprep.domain.recipe import Layout, OutputColumn, Recipe, RowRule, TransformSpec
from sugarprep.domain.result import PreparationResult
from sugarprep.validation.reports import BundleValidationReport, ResultValidationReport


MANIFEST_SCHEMA = ARTIFACT_SCHEMA_BY_NAME["manifest"].schema_id
PROFILE_SCHEMA = ARTIFACT_SCHEMA_BY_NAME["profile"].schema_id
COMPILED_PLAN_SCHEMA = ARTIFACT_SCHEMA_BY_NAME["compiled_plan"].schema_id
REJECTS_HEADER = ("source_row", "output_column", "source_column", "transform", "reason")


def serialize_draft_documents(
    *,
    recipe: Recipe,
    plan: PreparationPlan,
    profile: DatasetProfile,
    result: PreparationResult,
) -> tuple[ArtifactDocument, ...]:
    """Serialize every non-data, non-manifest production artifact."""

    return (
        _json_document("layout", _layout_payload(plan.layout)),
        _json_document("profile", _profile_payload(profile)),
        _json_document("compiled_plan", _compiled_plan_payload(recipe, plan)),
        _json_document("warnings", _warnings_payload(result)),
        ArtifactDocument(
            name="rejects",
            filename=PRODUCTION_ARTIFACT_FILENAMES["rejects"],
            media_type="text/csv",
            content=_rejects_content(result),
        ),
    )


def serialize_manifest_document(
    *,
    bundle_id: str,
    draft: ArtifactBundleDraft,
    manifest: ArtifactManifest,
    bundle_report: BundleValidationReport,
    acceptance: AcceptanceDecision,
) -> ArtifactDocument:
    result = draft.result
    output = result.output_snapshot
    if output is None:
        raise ValueError("cannot serialize a manifest without candidate output")
    payload: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA,
        "bundle_id": bundle_id,
        "draft_id": draft.draft_id,
        "draft_fingerprint": draft.draft_fingerprint,
        "state": "accepted",
        "recipe_name": draft.recipe.name,
        "plan_id": draft.plan.plan_id,
        "profile_id": draft.profile.profile_id,
        "source_sha256": draft.result.input_snapshot.content_sha256,
        "profile_mode": draft.profile.mode,
        "profiled_row_count": draft.profile.profiled_row_count,
        "profile_stop_reason": draft.profile.stop_reason,
        "row_count": output.row_count,
        "reject_count": len(result.rejected_rows),
        "warning_count": len(result.warnings),
        "masking_evidence": _masking_evidence_payload(
            draft.profile.snapshot.provenance.masking_evidence
        ),
        "cleaner_evidence": _cleaner_evidence_payload(
            draft.profile.snapshot.provenance.cleaner_evidence
        ),
        "artifacts": {
            _legacy_artifact_key(entry.name): entry.filename for entry in manifest.entries
        },
        "entries": [
            {
                "name": entry.name,
                "schema_id": ARTIFACT_SCHEMA_BY_NAME[entry.name].schema_id,
                "filename": entry.filename,
                "media_type": entry.media_type,
                "content_sha256": entry.content_sha256,
                "state": entry.state.value,
            }
            for entry in manifest.entries
        ],
        "validation": {
            "result": _result_report_payload(draft.result_validation_report),
            "bundle": _bundle_report_payload(bundle_report),
            "acceptance": {
                "decision_id": acceptance.decision_id,
                "accepted": acceptance.accepted,
                "accepted_by": acceptance.accepted_by,
                "decided_at": acceptance.decided_at.isoformat(),
                "validation_report_id": acceptance.validation_report_id,
            },
        },
    }
    return _json_document("manifest", payload)


def decode_json_document(document: ArtifactDocument) -> Any:
    return json.loads(document.content.decode("utf-8"))


def _json_document(name: str, payload: Any) -> ArtifactDocument:
    return ArtifactDocument(
        name=name,
        filename=PRODUCTION_ARTIFACT_FILENAMES[name],
        media_type="application/json",
        content=(json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _layout_payload(layout: Layout) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "time_col": layout.time_column,
        "time_kind": layout.time_kind,
        "value_cols": list(layout.value_columns),
        "primary_value_col": layout.primary_value_column,
        "missing_tokens": list(layout.missing_tokens),
        "missing_default": _plain(layout.missing_default),
        "sort_by_time": layout.sort_by_time,
        "dedupe": layout.dedupe,
    }
    if layout.entity_column is not None:
        payload["entity_col"] = layout.entity_column
    return payload


def _profile_payload(profile: DatasetProfile) -> dict[str, Any]:
    snapshot = profile.snapshot
    return {
        "schema_version": PROFILE_SCHEMA,
        "profile_id": profile.profile_id,
        "source_sha256": snapshot.content_sha256,
        "media_type": snapshot.media_type,
        "headers": list(snapshot.headers),
        "row_count": snapshot.row_count,
        "profiled_row_count": profile.profiled_row_count,
        "blank_row_count": profile.blank_row_count,
        "profile_mode": profile.mode,
        "stop_reason": profile.stop_reason,
        "provenance": _provenance_payload(snapshot),
        "columns": [asdict(column) for column in profile.columns],
    }


def _transform_payload(transform: TransformSpec) -> dict[str, Any]:
    return {"name": transform.name, "parameters": _plain(transform.parameters)}


def _output_column_payload(column: OutputColumn) -> dict[str, Any]:
    return {
        "name": column.name,
        "source": column.source,
        "sources": list(column.sources),
        "generate": column.generate,
        "derive": column.derive,
        "derive_parameters": _plain(column.derive_parameters),
        "transforms": [_transform_payload(transform) for transform in column.transforms],
    }


def _row_rule_payload(rule: RowRule) -> dict[str, Any]:
    return {
        "name": rule.name,
        "column": rule.column,
        "action": rule.action,
        "parameters": _plain(rule.parameters),
    }


def _compiled_plan_payload(recipe: Recipe, plan: PreparationPlan) -> dict[str, Any]:
    snapshot = plan.input_snapshot
    return {
        "schema_version": COMPILED_PLAN_SCHEMA,
        "plan_id": plan.plan_id,
        "version": plan.version,
        "recipe_name": plan.recipe_name,
        "input": {
            "dataset_id": snapshot.reference.dataset_id,
            "content_sha256": snapshot.content_sha256,
            "media_type": snapshot.media_type,
            "headers": list(snapshot.headers),
            "row_count": snapshot.row_count,
            "provenance": _provenance_payload(snapshot),
        },
        "recipe": {
            "version": recipe.version,
            "name": recipe.name,
            "expected_headers": list(recipe.expected_headers),
        },
        "output_columns": [_output_column_payload(column) for column in plan.output_columns],
        "layout": _layout_payload(plan.layout),
        "row_rules": [_row_rule_payload(rule) for rule in plan.row_rules],
        "reject_policy": plan.reject_policy,
    }


def _warnings_payload(result: PreparationResult) -> list[dict[str, str]]:
    return [{"message": warning} for warning in result.warnings]


def _rejects_content(result: PreparationResult) -> bytes:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=REJECTS_HEADER, lineterminator="\n")
    writer.writeheader()
    for row in result.rejected_rows:
        writer.writerow(
            {
                "source_row": row.source_row_number,
                "output_column": "",
                "source_column": "",
                "transform": row.reason_code,
                "reason": row.message,
            }
        )
    return output.getvalue().encode("utf-8")


def _finding_payload(finding: Any) -> dict[str, str]:
    return {
        "code": finding.code,
        "message": finding.message,
        "severity": finding.severity.value,
    }


def _masking_evidence_payload(evidence: Any) -> dict[str, Any] | None:
    if evidence is None:
        return None
    return {
        "evidence_id": evidence.evidence_id,
        "algorithm": evidence.algorithm,
        "input_sha256": evidence.input_sha256,
        "row_count": evidence.row_count,
        "cell_count": evidence.cell_count,
        "masked_cell_count": evidence.masked_cell_count,
        "model_provider_id": evidence.model_provider_id,
        "model_detection_count": evidence.model_detection_count,
        "deterministic_detection_count": evidence.deterministic_detection_count,
        "finding_count": evidence.finding_count,
        "findings": [asdict(finding) for finding in evidence.findings],
    }


def _cleaner_evidence_payload(evidence: Any) -> dict[str, Any] | None:
    if evidence is None:
        return None
    return {
        "evidence_id": evidence.evidence_id,
        "plan_candidate_id": evidence.plan_candidate_id,
        "provider_id": evidence.provider_id,
        "plan_id": evidence.plan_id,
        "input_sha256": evidence.input_sha256,
        "output_sha256": evidence.output_sha256,
        "rows_quarantined": evidence.rows_quarantined,
        "validation_passed": evidence.validation_passed,
        "tool_executions": [asdict(item) for item in evidence.tool_executions],
    }


def _provenance_payload(snapshot: Any) -> dict[str, Any]:
    provenance = snapshot.provenance
    return {
        "operation": provenance.operation,
        "parent_sha256": list(provenance.parent_sha256),
        "masking_evidence": _masking_evidence_payload(provenance.masking_evidence),
        "cleaner_evidence": _cleaner_evidence_payload(provenance.cleaner_evidence),
    }


def _result_report_payload(report: ResultValidationReport) -> dict[str, Any]:
    return {
        "report_id": report.report_id,
        "plan_id": report.plan_id,
        "input_sha256": report.input_sha256,
        "output_sha256": report.output_sha256,
        "passed": report.passed,
        "findings": [_finding_payload(finding) for finding in report.findings],
    }


def _bundle_report_payload(report: BundleValidationReport) -> dict[str, Any]:
    return {
        "report_id": report.report_id,
        "draft_id": report.draft_id,
        "draft_fingerprint": report.draft_fingerprint,
        "passed": report.passed,
        "findings": [_finding_payload(finding) for finding in report.findings],
    }


def _legacy_artifact_key(name: str) -> str:
    return {
        "prepared_data": "data_csv",
        "layout": "layout_json",
        "profile": "profile_json",
        "compiled_plan": "compiled_plan_json",
        "warnings": "warnings_json",
        "rejects": "rejects_csv",
        "manifest": "manifest_json",
    }[name]
