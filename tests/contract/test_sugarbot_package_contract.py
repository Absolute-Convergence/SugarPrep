from __future__ import annotations

import json
from pathlib import Path

from sugarprep.artifacts import PRODUCTION_ARTIFACT_FILENAMES, PRODUCTION_ARTIFACT_SCHEMAS
from sugarprep.validation.sugarbot_contract import (
    EXPECTED_REJECTS_HEADER,
    REQUIRED_SUGARBOT_ARTIFACTS,
    validate_sugarbot_package,
)


FIXTURE = Path("tests/fixtures/sugarbot_package_v1.json")


def test_producer_and_consumer_match_the_frozen_package_fixture() -> None:
    contract = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert tuple(contract["required_files"]) == REQUIRED_SUGARBOT_ARTIFACTS
    assert set(PRODUCTION_ARTIFACT_FILENAMES.values()) == set(REQUIRED_SUGARBOT_ARTIFACTS)
    assert {schema.filename for schema in PRODUCTION_ARTIFACT_SCHEMAS} == set(REQUIRED_SUGARBOT_ARTIFACTS)
    assert {schema.top_level_shape for schema in PRODUCTION_ARTIFACT_SCHEMAS} <= {"array", "csv", "object"}
    assert next(schema for schema in PRODUCTION_ARTIFACT_SCHEMAS if schema.name == "manifest").declares_content_digest is False
    assert tuple(contract["rejects_header"]) == EXPECTED_REJECTS_HEADER
    assert contract["manifest_artifacts"] == {
        filename.replace(".", "_").replace("-", "_"): filename
        for filename in REQUIRED_SUGARBOT_ARTIFACTS
    }


def test_consumer_contract_rejects_wrapped_layout() -> None:
    contract = json.loads(FIXTURE.read_text(encoding="utf-8"))
    manifest = {
        "schema_version": "sugarprep.artifact-manifest.v1",
        "row_count": 1,
        "source_sha256": "a" * 64,
        "artifacts": contract["manifest_artifacts"],
    }
    files = {
        "data.csv": b"date,value\n2026-08-09,1\n",
        "layout.json": b'{"data_spec":{"time_col":"date"}}\n',
        "manifest.json": (json.dumps(manifest) + "\n").encode("utf-8"),
        "profile.json": (json.dumps({"source_sha256": "a" * 64}) + "\n").encode("utf-8"),
        "compiled-plan.json": b'{"schema_version":"sugarprep.compiled-plan.v1"}\n',
        "warnings.json": b"[]\n",
        "rejects.csv": (",".join(contract["rejects_header"]) + "\n").encode("utf-8"),
    }

    report = validate_sugarbot_package(files)

    assert not report.passed
    assert "sugarbot.layout_wrapped" in {finding.code for finding in report.findings}
