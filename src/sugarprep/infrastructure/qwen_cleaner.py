"""Local Unsloth provider for the retained Qwen Cleaner adapter."""

from __future__ import annotations

from collections.abc import Iterable
import json
from pathlib import Path
import subprocess
from typing import Any

from sugarprep.domain.errors import SugarPrepError
from sugarprep.inference.cleaner import (
    CLEANER_RUNNER_REQUEST_VERSION,
    CleanerPlanError,
    cleaner_completion_prompt,
    parse_cleaner_tool_plan_response,
)


class QwenCleanerProviderError(SugarPrepError):
    pass


class QwenCleanerProvider:
    """Invoke the proven Cleaner adapter through the local Unsloth CLI."""

    def __init__(
        self,
        *,
        provider_id: str,
        model_path: Path,
        unsloth_command: Path,
        top_p: float = 0.8,
        top_k: int = 20,
        repetition_penalty: float = 1.0,
        max_seq_length: int = 4096,
        load_in_4bit: bool = True,
        timeout_seconds: int | None = None,
    ) -> None:
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("provider_id must be non-empty")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive when supplied")
        self._provider_id = provider_id.strip()
        self._model_path = model_path.resolve()
        self._unsloth_command = unsloth_command.resolve()
        self._top_p = top_p
        self._top_k = top_k
        self._repetition_penalty = repetition_penalty
        self._max_seq_length = max_seq_length
        self._load_in_4bit = load_in_4bit
        self._timeout_seconds = timeout_seconds

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def generate(self, request: dict[str, Any]) -> str:
        self._validate_local_assets()
        messages = _request_messages(request)
        if request.get("schema_version") != CLEANER_RUNNER_REQUEST_VERSION:
            raise QwenCleanerProviderError(
                f"request.schema_version must be {CLEANER_RUNNER_REQUEST_VERSION}"
            )
        if request.get("task") != "propose_cleaner_tool_plan":
            raise QwenCleanerProviderError("request.task must be propose_cleaner_tool_plan")
        prompt_transport = request.get("prompt_transport", "chat")
        if prompt_transport not in {"chat", "completion"}:
            raise QwenCleanerProviderError("request.prompt_transport must be chat or completion")
        options = request.get("runner_options")
        if not isinstance(options, dict):
            options = {}
        max_new_tokens = _positive_int(options.get("max_new_tokens", 4096), "max_new_tokens")
        temperature = _non_negative_float(options.get("temperature", 0.1), "temperature")
        system_prompt = messages[0]["content"]
        prompt = (
            cleaner_completion_prompt(messages)
            if prompt_transport == "completion"
            else "\n\n".join(message["content"] for message in messages[1:])
        )
        args = [
            str(self._unsloth_command),
            "inference",
            str(self._model_path),
            prompt,
            "--max-new-tokens",
            str(max_new_tokens),
            "--temperature",
            str(temperature),
            "--top-p",
            str(self._top_p),
            "--top-k",
            str(self._top_k),
            "--repetition-penalty",
            str(self._repetition_penalty),
            "--max-seq-length",
            str(self._max_seq_length),
        ]
        if prompt_transport == "chat":
            args.extend(["--system-prompt", system_prompt])
        args.append("--load-in-4bit" if self._load_in_4bit else "--no-load-in-4bit")
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=self._timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise QwenCleanerProviderError(f"Qwen Cleaner inference could not run: {exc}") from exc
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        _write_raw_output(request.get("raw_output_path"), output)
        if completed.returncode != 0:
            raise QwenCleanerProviderError(
                f"Qwen Cleaner inference exited with code {completed.returncode}: {_tail(output)}"
            )
        if not output.strip():
            raise QwenCleanerProviderError("Qwen Cleaner inference produced no output")
        return _extract_valid_plan_json(output)

    def _validate_local_assets(self) -> None:
        if not self._model_path.is_dir():
            raise QwenCleanerProviderError("configured Qwen Cleaner model directory does not exist")
        required = ("adapter_config.json", "adapter_model.safetensors", "tokenizer.json")
        missing = [name for name in required if not (self._model_path / name).is_file()]
        if missing:
            raise QwenCleanerProviderError(
                "configured Qwen Cleaner model is incomplete: " + ", ".join(missing)
            )
        if not self._unsloth_command.is_file():
            raise QwenCleanerProviderError("configured Unsloth executable does not exist")


def _request_messages(request: dict[str, Any]) -> list[dict[str, str]]:
    messages = request.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        raise QwenCleanerProviderError("request.messages must contain system and user messages")
    normalized: list[dict[str, str]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise QwenCleanerProviderError(f"request.messages[{index}] must be an object")
        role = message.get("role")
        content = message.get("content")
        if not isinstance(role, str) or not isinstance(content, str) or not content:
            raise QwenCleanerProviderError(
                f"request.messages[{index}] must include role and content strings"
            )
        normalized.append({"role": role, "content": content})
    if normalized[0]["role"] != "system":
        raise QwenCleanerProviderError("request.messages[0] must be the system message")
    return normalized


def _extract_valid_plan_json(text: str) -> str:
    errors: list[str] = []
    plan_candidate_errors: list[str] = []
    for candidate in _iter_json_object_strings(text):
        try:
            plan = parse_cleaner_tool_plan_response(candidate)
        except (CleanerPlanError, json.JSONDecodeError, ValueError) as exc:
            errors.append(str(exc))
            if "sugarprep.cleaner_tool_plan.v1" in candidate:
                plan_candidate_errors.append(str(exc))
            continue
        return json.dumps(plan.to_dict(), separators=(",", ":"), sort_keys=True)
    diagnostic_errors = plan_candidate_errors or errors
    detail = f" Last schema error: {diagnostic_errors[-1]}" if diagnostic_errors else ""
    raise QwenCleanerProviderError(
        "model output did not contain a valid CleanerToolPlan JSON object." + detail
    )


def _iter_json_object_strings(text: str) -> Iterable[str]:
    for start, char in enumerate(text):
        if char != "{":
            continue
        end = _matching_json_object_end(text, start)
        if end is not None:
            yield text[start : end + 1]


def _matching_json_object_end(text: str, start: int) -> int | None:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _write_raw_output(value: Any, output: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value:
        raise QwenCleanerProviderError("request.raw_output_path must be a non-empty string or null")
    path = Path(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output, encoding="utf-8")


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise QwenCleanerProviderError(f"runner option {name} must be a positive integer")
    return value


def _non_negative_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise QwenCleanerProviderError(f"runner option {name} must be a non-negative number")
    return float(value)


def _tail(text: str, *, max_chars: int = 2000) -> str:
    stripped = text.strip()
    return stripped if len(stripped) <= max_chars else stripped[-max_chars:]
