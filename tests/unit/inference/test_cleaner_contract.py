from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sugarprep.inference.cleaner import (
    CLEANER_CONTEXT_VERSION,
    CLEANER_TOOL_NAMES,
    CleanerInferenceService,
    CleanerPlanError,
    build_cleaner_messages,
    build_cleaner_runner_request,
    parse_cleaner_tool_plan_response,
)


def execute_plan_payload() -> dict[str, object]:
    return {
        "version": "sugarprep.cleaner_tool_plan.v1",
        "plan_id": "baseline-plan",
        "stop_reason": "execute",
        "tool_calls": [
            {
                "call_id": "detect-001",
                "tool_name": "detect_file_format",
                "arguments": {},
                "purpose": "Inspect the input format.",
                "preconditions": [],
                "metadata": {},
            },
            {
                "call_id": "normalize-002",
                "tool_name": "normalize_column_names",
                "arguments": {"header_mapping": ["Date", "close", "volume"]},
                "purpose": "Normalize headers.",
                "preconditions": [],
                "metadata": {},
            },
            {
                "call_id": "validate-003",
                "tool_name": "validate_parseable_table",
                "arguments": {},
                "purpose": "Validate the candidate.",
                "preconditions": [],
                "metadata": {},
            },
        ],
        "unknowns": [],
        "warnings": [],
        "diagnostics": {},
        "metadata": {"model": "qwen35-4b-cleaner-sft-v1-full"},
    }


def cleaner_context() -> dict[str, object]:
    return {
        "schema_version": CLEANER_CONTEXT_VERSION,
        "case_id": "runtime-001",
        "variant_index": 1,
        "case_seed": 0,
        "user_request": "Normalize this table for profiling.",
        "source_preview": ["Date, close,volume", "2026-01-01, 2,10"],
        "available_tools": sorted(CLEANER_TOOL_NAMES),
        "pre_repair_detection": {"delimiter": ",", "source_path": "C:/private/input.csv"},
        "pre_repair_validation": {"parseable": True, "profile_file": "C:/private/profile.json"},
        "observed_issues": ["header_whitespace"],
        "metadata": {"source": "runtime"},
    }


def test_proven_execute_plan_parses_with_full_tool_vocabulary() -> None:
    plan = parse_cleaner_tool_plan_response(json.dumps(execute_plan_payload()))

    assert tuple(call.tool_name for call in plan.tool_calls) == (
        "detect_file_format",
        "normalize_column_names",
        "validate_parseable_table",
    )
    assert plan.execution_requests()[1]["arguments"] == {
        "header_mapping": ["Date", "close", "volume"]
    }
    assert len(CLEANER_TOOL_NAMES) == 14


def test_cleaner_plan_rejects_aliases_and_response_repair() -> None:
    payload = execute_plan_payload()
    tool_calls = payload["tool_calls"]
    assert isinstance(tool_calls, list)
    first_call = tool_calls[0]
    assert isinstance(first_call, dict)
    first_call["tool_name"] = "normalize_headers"

    with pytest.raises(CleanerPlanError, match="not supported"):
        parse_cleaner_tool_plan_response(json.dumps(payload))
    with pytest.raises(CleanerPlanError, match="strict JSON"):
        parse_cleaner_tool_plan_response("```json\n{}\n```")


def test_trained_prompt_scrubs_paths_without_reshaping_context() -> None:
    messages = build_cleaner_messages(cleaner_context())
    user_payload = json.loads(messages[1]["content"])

    assert messages[0]["role"] == "system"
    assert user_payload["schema_version"] == CLEANER_CONTEXT_VERSION
    assert "source_path" not in user_payload["pre_repair_detection"]
    assert "profile_file" not in user_payload["pre_repair_validation"]
    assert user_payload["source_preview"][0] == "Date, close,volume"


def test_trained_prompt_injects_and_guards_the_runtime_tool_vocabulary() -> None:
    messages = build_cleaner_messages({"user_request": "Clean the bounded source evidence."})
    user_payload = json.loads(messages[1]["content"])

    assert user_payload["schema_version"] == CLEANER_CONTEXT_VERSION
    assert user_payload["available_tools"] == sorted(CLEANER_TOOL_NAMES)

    with pytest.raises(CleanerPlanError, match="runtime tool vocabulary"):
        build_cleaner_messages({"available_tools": ["date"]})


def test_runner_request_matches_proven_outer_envelope() -> None:
    request = build_cleaner_runner_request(
        cleaner_context(),
        case_id="runtime-001",
        source_csv=Path("input.csv"),
        model="cleaner-adapter",
    )

    assert tuple(request) == (
        "schema_version",
        "task",
        "response_mode",
        "prompt_transport",
        "runner_options",
        "model",
        "raw_output_path",
        "case_id",
        "source_csv",
        "messages",
    )
    assert request["task"] == "propose_cleaner_tool_plan"
    assert request["prompt_transport"] == "chat"


class StaticCleanerProvider:
    provider_id = "qwen-cleaner-test"

    def __init__(self, response: str) -> None:
        self.response = response
        self.request: dict[str, object] | None = None

    def generate(self, request: dict[str, object]) -> str:
        self.request = request
        return self.response


def test_candidate_is_bound_to_source_digest() -> None:
    provider = StaticCleanerProvider(json.dumps(execute_plan_payload()))
    service = CleanerInferenceService(provider)
    digest = hashlib.sha256(b"Date,close\n2026-01-01,2\n").hexdigest()

    candidate = service.propose(
        context=cleaner_context(),
        source_sha256=digest,
        case_id="runtime-001",
        source_csv=Path("input.csv"),
        model="cleaner-adapter",
        raw_output_path=Path("raw-output.txt"),
    )

    assert candidate.source_sha256 == digest
    assert candidate.plan.stop_reason == "execute"
    assert candidate.candidate_id.startswith("cleaner-candidate-")
    assert provider.request is not None
    assert provider.request["raw_output_path"] == "raw-output.txt"
