"""Authoritative schema registry for production artifact documents."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ArtifactSchema:
    name: str
    filename: str
    media_type: str
    schema_id: str
    top_level_shape: str
    declares_content_digest: bool = True


PRODUCTION_ARTIFACT_SCHEMAS = (
    ArtifactSchema("prepared_data", "data.csv", "text/csv", "sugarprep.prepared-data.v1", "csv"),
    ArtifactSchema("layout", "layout.json", "application/json", "sugarbot.data-spec.v1", "object"),
    ArtifactSchema(
        "profile",
        "profile.json",
        "application/json",
        "sugarprep.dataset-profile.v1",
        "object",
    ),
    ArtifactSchema(
        "compiled_plan",
        "compiled-plan.json",
        "application/json",
        "sugarprep.compiled-plan.v1",
        "object",
    ),
    ArtifactSchema("warnings", "warnings.json", "application/json", "sugarprep.warnings.v1", "array"),
    ArtifactSchema("rejects", "rejects.csv", "text/csv", "sugarprep.rejects.v1", "csv"),
    ArtifactSchema(
        "manifest",
        "manifest.json",
        "application/json",
        "sugarprep.artifact-manifest.v1",
        "object",
        declares_content_digest=False,
    ),
)

ARTIFACT_SCHEMA_BY_NAME = {schema.name: schema for schema in PRODUCTION_ARTIFACT_SCHEMAS}

if len(ARTIFACT_SCHEMA_BY_NAME) != len(PRODUCTION_ARTIFACT_SCHEMAS):
    raise RuntimeError("production artifact schema names must be unique")
if len({schema.filename for schema in PRODUCTION_ARTIFACT_SCHEMAS}) != len(PRODUCTION_ARTIFACT_SCHEMAS):
    raise RuntimeError("production artifact schema filenames must be unique")
