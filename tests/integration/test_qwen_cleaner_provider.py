from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from sugarprep.inference.cleaner import build_cleaner_runner_request, parse_cleaner_tool_plan_response
from sugarprep.infrastructure.qwen_cleaner import QwenCleanerProvider


def plan_json() -> str:
    return json.dumps(
        {
            "version": "sugarprep.cleaner_tool_plan.v1",
            "plan_id": "runtime-plan",
            "stop_reason": "execute",
            "tool_calls": [
                {
                    "call_id": "normalize-001",
                    "tool_name": "normalize_column_names",
                    "arguments": {},
                    "purpose": "Normalize headers.",
                    "preconditions": [],
                    "metadata": {},
                }
            ],
            "unknowns": [],
            "warnings": [],
            "diagnostics": {},
            "metadata": {},
        }
    )


def make_provider(tmp_path: Path) -> QwenCleanerProvider:
    model_path = tmp_path / "cleaner"
    model_path.mkdir()
    for name in ("adapter_config.json", "adapter_model.safetensors", "tokenizer.json"):
        (model_path / name).write_text("fixture", encoding="utf-8")
    command = tmp_path / "unsloth.exe"
    command.write_text("fixture", encoding="utf-8")
    return QwenCleanerProvider(
        provider_id="qwen-cleaner-test",
        model_path=model_path,
        unsloth_command=command,
    )


def test_qwen_provider_uses_proven_chat_invocation_and_extracts_plan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider = make_provider(tmp_path)
    raw_output_path = tmp_path / "raw" / "output.txt"
    request = build_cleaner_runner_request(
        {"schema_version": "sugarprep.cleaner_curriculum_context.v1", "source_preview": ["a,b"]},
        case_id="runtime-001",
        source_csv=tmp_path / "input.csv",
        raw_output_path=raw_output_path,
    )
    observed: dict[str, object] = {}

    def fake_run(args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout=f"loading model\n{plan_json()}\n", stderr="done")

    monkeypatch.setattr("sugarprep.infrastructure.qwen_cleaner.subprocess.run", fake_run)

    response = provider.generate(request)
    plan = parse_cleaner_tool_plan_response(response)
    args = observed["args"]
    assert isinstance(args, list)
    assert args[1] == "inference"
    assert "--system-prompt" in args
    assert "--load-in-4bit" in args
    assert plan.tool_calls[0].tool_name == "normalize_column_names"
    assert raw_output_path.read_text(encoding="utf-8").startswith("loading model")
