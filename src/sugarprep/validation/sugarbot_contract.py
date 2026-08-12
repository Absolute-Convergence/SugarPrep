"""Consumer-shaped validation for serialized SugarBot preparation packages."""

from __future__ import annotations

from collections.abc import Mapping
import csv
import hashlib
from io import StringIO
import json
from typing import Any

from sugarprep.validation.reports import SugarBotContractReport, ValidationFinding


# Deliberately consumer-owned: do not import the producer's artifact constants here.
REQUIRED_SUGARBOT_ARTIFACTS = (
    "data.csv",
    "layout.json",
    "manifest.json",
    "profile.json",
    "compiled-plan.json",
    "warnings.json",
    "rejects.csv",
)
EXPECTED_REJECTS_HEADER = ("source_row", "output_column", "source_column", "transform", "reason")


def validate_sugarbot_package(files: Mapping[str, bytes]) -> SugarBotContractReport:
    """Validate a package without interpreting any dataset storage locator."""

    findings: list[ValidationFinding] = []
    missing = [filename for filename in REQUIRED_SUGARBOT_ARTIFACTS if filename not in files]
    for filename in missing:
        findings.append(ValidationFinding("sugarbot.artifact_missing", f"missing package artifact: {filename}"))
    if not missing:
        data_header, row_count = _read_data(files["data.csv"], findings)
        layout = _read_json_object(files["layout.json"], "layout.json", findings)
        manifest = _read_json_object(files["manifest.json"], "manifest.json", findings)
        profile = _read_json_object(files["profile.json"], "profile.json", findings)
        compiled_plan = _read_json_object(files["compiled-plan.json"], "compiled-plan.json", findings)
        warnings = _read_json(files["warnings.json"], "warnings.json", findings)
        _validate_rejects(files["rejects.csv"], findings)
        _validate_layout(layout, data_header, findings)
        _validate_manifest(manifest, profile, row_count, findings)
        if compiled_plan and compiled_plan.get("schema_version") != "sugarprep.compiled-plan.v1":
            findings.append(
                ValidationFinding("sugarbot.compiled_plan_schema", "compiled-plan.json schema is unsupported")
            )
        if warnings is not None and not isinstance(warnings, list):
            findings.append(ValidationFinding("sugarbot.warnings_shape", "warnings.json must be a JSON list"))

    report_payload = [
        {"code": finding.code, "message": finding.message, "severity": finding.severity.value}
        for finding in findings
    ]
    encoded = json.dumps(report_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return SugarBotContractReport(
        report_id=f"sugarbot-contract-{hashlib.sha256(encoded).hexdigest()[:24]}",
        findings=tuple(findings),
    )


def _read_json(content: bytes, label: str, findings: list[ValidationFinding]) -> Any:
    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        findings.append(ValidationFinding("sugarbot.json_invalid", f"{label} is not valid JSON: {error}"))
        return None


def _read_json_object(content: bytes, label: str, findings: list[ValidationFinding]) -> dict[str, Any]:
    payload = _read_json(content, label, findings)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        findings.append(ValidationFinding("sugarbot.json_object_required", f"{label} must be a JSON object"))
        return {}
    return payload


def _read_data(content: bytes, findings: list[ValidationFinding]) -> tuple[list[str], int]:
    try:
        reader = csv.reader(StringIO(content.decode("utf-8-sig"), newline=""))
        header = next(reader)
        row_count = sum(1 for _ in reader)
    except (UnicodeDecodeError, StopIteration, csv.Error) as error:
        findings.append(ValidationFinding("sugarbot.data_invalid", f"data.csv is invalid: {error}"))
        return [], 0
    if not header:
        findings.append(ValidationFinding("sugarbot.data_header_empty", "data.csv header is empty"))
    return header, row_count


def _validate_rejects(content: bytes, findings: list[ValidationFinding]) -> None:
    try:
        reader = csv.reader(StringIO(content.decode("utf-8-sig"), newline=""))
        header = tuple(next(reader))
    except (UnicodeDecodeError, StopIteration, csv.Error) as error:
        findings.append(ValidationFinding("sugarbot.rejects_invalid", f"rejects.csv is invalid: {error}"))
        return
    if header != EXPECTED_REJECTS_HEADER:
        findings.append(
            ValidationFinding("sugarbot.rejects_header", "rejects.csv does not use the production header")
        )


def _validate_layout(
    layout: dict[str, Any],
    data_header: list[str],
    findings: list[ValidationFinding],
) -> None:
    wrappers = [key for key in ("ingest", "data_spec") if key in layout]
    if wrappers:
        findings.append(
            ValidationFinding("sugarbot.layout_wrapped", "layout.json must be a raw SugarBot DataSpec")
        )
    time_col = layout.get("time_col")
    value_cols = layout.get("value_cols")
    primary = layout.get("primary_value_col")
    if not isinstance(time_col, str) or not time_col:
        findings.append(ValidationFinding("sugarbot.layout_time_col", "layout.json requires time_col"))
    elif time_col not in data_header:
        findings.append(ValidationFinding("sugarbot.layout_time_missing", "layout time_col is absent from data"))
    if not isinstance(value_cols, list) or not value_cols or not all(isinstance(item, str) for item in value_cols):
        findings.append(
            ValidationFinding("sugarbot.layout_value_cols", "layout value_cols must be a non-empty string list")
        )
        return
    if any(column not in data_header for column in value_cols):
        findings.append(
            ValidationFinding("sugarbot.layout_values_missing", "layout value_cols are absent from data")
        )
    if not isinstance(primary, str) or not primary:
        findings.append(
            ValidationFinding("sugarbot.layout_primary_value", "layout requires primary_value_col")
        )
    elif primary not in value_cols:
        findings.append(
            ValidationFinding("sugarbot.layout_primary_membership", "primary_value_col must be in value_cols")
        )


def _validate_manifest(
    manifest: dict[str, Any],
    profile: dict[str, Any],
    row_count: int,
    findings: list[ValidationFinding],
) -> None:
    if manifest.get("schema_version") != "sugarprep.artifact-manifest.v1":
        findings.append(ValidationFinding("sugarbot.manifest_schema", "manifest schema is unsupported"))
    if manifest.get("row_count") != row_count:
        findings.append(
            ValidationFinding("sugarbot.manifest_row_count", "manifest row_count does not match data.csv")
        )
    manifest_sha = manifest.get("source_sha256")
    profile_sha = profile.get("source_sha256")
    if manifest_sha and profile_sha and manifest_sha != profile_sha:
        findings.append(
            ValidationFinding("sugarbot.manifest_source_sha", "manifest and profile source digests differ")
        )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        findings.append(ValidationFinding("sugarbot.manifest_artifacts", "manifest artifacts must be an object"))
        return
    for filename in REQUIRED_SUGARBOT_ARTIFACTS:
        key = filename.replace(".", "_").replace("-", "_")
        if artifacts.get(key) != filename:
            findings.append(
                ValidationFinding(
                    "sugarbot.manifest_artifact_mapping",
                    f"manifest artifacts.{key} must be {filename}",
                )
            )
