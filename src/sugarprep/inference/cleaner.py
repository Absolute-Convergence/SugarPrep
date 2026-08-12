"""Exact Qwen Cleaner request and strict ``CleanerToolPlan`` contract.

This module intentionally models one retained artifact. It is not a generic
text-generation interface: the prompt, request envelope, stop reasons, and
deterministic tool vocabulary are the contract used by the proven Cleaner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol


CLEANER_CONTEXT_VERSION = "sugarprep.cleaner_curriculum_context.v1"
CLEANER_RUNNER_REQUEST_VERSION = "sugarprep.cleaner_runner_request.v1"
CLEANER_TOOL_PLAN_VERSION = "sugarprep.cleaner_tool_plan.v1"
CLEANER_STOP_REASONS = frozenset({"execute", "needs_user_input", "cannot_repair"})
CLEANER_TOOL_NAMES = frozenset(
    {
        "detect_file_format",
        "select_header_row",
        "flatten_multirow_header",
        "trim_preamble_footer",
        "repair_ragged_rows",
        "normalize_column_names",
        "normalize_missing_tokens",
        "parse_flexible_number",
        "parse_datetime",
        "join_datetime_parts",
        "normalize_wide_periods",
        "split_compound_column",
        "deduplicate_rows",
        "validate_parseable_table",
    }
)
CLEANER_PLAN_FIELDS = frozenset(
    {
        "version",
        "plan_id",
        "stop_reason",
        "tool_calls",
        "unknowns",
        "warnings",
        "diagnostics",
        "metadata",
    }
)
CLEANER_TOOL_CALL_FIELDS = frozenset(
    {"call_id", "tool_name", "arguments", "purpose", "preconditions", "metadata"}
)
PATH_LIKE_PROMPT_KEYS = frozenset(
    {
        "source_file",
        "source_path",
        "source_csv",
        "output_file",
        "output_path",
        "profile_file",
        "profile_path",
        "profile_json",
    }
)
CLEANER_SYSTEM_PROMPT = (
    "You are the SugarPrep Cleaner. Return exactly one strict CleanerToolPlan JSON object. "
    "The root object must contain exactly these keys: "
    + ", ".join(
        (
            "version",
            "plan_id",
            "stop_reason",
            "tool_calls",
            "unknowns",
            "warnings",
            "diagnostics",
            "metadata",
        )
    )
    + ". "
    "version must be sugarprep.cleaner_tool_plan.v1. "
    "stop_reason must be one of: execute, needs_user_input, cannot_repair. "
    "unknowns and warnings must be arrays of strings. "
    "diagnostics and metadata must be objects. "
    "When stop_reason is execute, tool_calls must be a non-empty array of deterministic Cleaner tools. "
    "When stop_reason is needs_user_input or cannot_repair, tool_calls must be empty. "
    "Use only named deterministic tools. Never invent transforms, formulas, code, or tool names. "
    "Return raw JSON only."
)


class CleanerPlanError(ValueError):
    """Raised when Qwen output does not match its trained plan contract."""


@dataclass(frozen=True, slots=True)
class CleanerPlannedToolCall:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None
    purpose: str | None = None
    preconditions: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "call_id", _optional_string(self.call_id, "tool_call.call_id"))
        tool_name = _required_string(self.tool_name, "tool_call.tool_name")
        if tool_name not in CLEANER_TOOL_NAMES:
            raise CleanerPlanError(f"tool_call.tool_name is not supported: {tool_name}")
        object.__setattr__(self, "tool_name", tool_name)
        object.__setattr__(self, "arguments", _mapping(self.arguments, "tool_call.arguments"))
        object.__setattr__(self, "purpose", _optional_string(self.purpose, "tool_call.purpose"))
        object.__setattr__(
            self,
            "preconditions",
            _string_tuple(self.preconditions, "tool_call.preconditions"),
        )
        object.__setattr__(self, "metadata", _mapping(self.metadata, "tool_call.metadata"))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CleanerPlannedToolCall":
        _require_exact_keys(raw, CLEANER_TOOL_CALL_FIELDS, "tool_call")
        return cls(
            call_id=raw["call_id"],
            tool_name=raw["tool_name"],
            arguments=raw["arguments"],
            purpose=raw["purpose"],
            preconditions=raw["preconditions"],
            metadata=raw["metadata"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "purpose": self.purpose,
            "preconditions": list(self.preconditions),
            "metadata": self.metadata,
        }

    def to_execution_request(self, *, index: int) -> dict[str, Any]:
        return {
            "call_id": self.call_id or f"cleaner-{index:03d}",
            "tool_name": self.tool_name,
            "arguments": self.arguments,
        }


@dataclass(frozen=True, slots=True)
class CleanerToolPlan:
    plan_id: str
    stop_reason: str
    tool_calls: tuple[CleanerPlannedToolCall, ...] = ()
    unknowns: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = CLEANER_TOOL_PLAN_VERSION

    def __post_init__(self) -> None:
        if self.version != CLEANER_TOOL_PLAN_VERSION:
            raise CleanerPlanError(f"cleaner_plan.version must be {CLEANER_TOOL_PLAN_VERSION}")
        object.__setattr__(self, "plan_id", _required_string(self.plan_id, "cleaner_plan.plan_id"))
        stop_reason = _required_string(self.stop_reason, "cleaner_plan.stop_reason")
        if stop_reason not in CLEANER_STOP_REASONS:
            raise CleanerPlanError(f"cleaner_plan.stop_reason is not supported: {stop_reason}")
        object.__setattr__(self, "stop_reason", stop_reason)
        calls = tuple(
            call if isinstance(call, CleanerPlannedToolCall) else CleanerPlannedToolCall.from_dict(call)
            for call in self.tool_calls
        )
        object.__setattr__(self, "tool_calls", calls)
        object.__setattr__(self, "unknowns", _string_tuple(self.unknowns, "cleaner_plan.unknowns"))
        object.__setattr__(self, "warnings", _string_tuple(self.warnings, "cleaner_plan.warnings"))
        object.__setattr__(self, "diagnostics", _mapping(self.diagnostics, "cleaner_plan.diagnostics"))
        object.__setattr__(self, "metadata", _mapping(self.metadata, "cleaner_plan.metadata"))
        if stop_reason == "execute" and not calls:
            raise CleanerPlanError("cleaner_plan.tool_calls must not be empty when stop_reason is execute")
        if stop_reason != "execute" and calls:
            raise CleanerPlanError("cleaner_plan.tool_calls must be empty unless stop_reason is execute")
        if stop_reason == "needs_user_input" and not self.unknowns:
            raise CleanerPlanError("cleaner_plan.unknowns must explain needed user input")
        if stop_reason == "cannot_repair" and not self.diagnostics:
            raise CleanerPlanError("cleaner_plan.diagnostics must explain cannot_repair")

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CleanerToolPlan":
        _require_exact_keys(raw, CLEANER_PLAN_FIELDS, "cleaner_plan")
        tool_calls = raw["tool_calls"]
        if not isinstance(tool_calls, list) or not all(isinstance(item, dict) for item in tool_calls):
            raise CleanerPlanError("cleaner_plan.tool_calls must be an object list")
        return cls(
            version=raw["version"],
            plan_id=raw["plan_id"],
            stop_reason=raw["stop_reason"],
            tool_calls=tuple(CleanerPlannedToolCall.from_dict(item) for item in tool_calls),
            unknowns=raw["unknowns"],
            warnings=raw["warnings"],
            diagnostics=raw["diagnostics"],
            metadata=raw["metadata"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "plan_id": self.plan_id,
            "stop_reason": self.stop_reason,
            "tool_calls": [call.to_dict() for call in self.tool_calls],
            "unknowns": list(self.unknowns),
            "warnings": list(self.warnings),
            "diagnostics": self.diagnostics,
            "metadata": self.metadata,
        }

    def execution_requests(self) -> tuple[dict[str, Any], ...]:
        if self.stop_reason != "execute":
            return ()
        return tuple(call.to_execution_request(index=index) for index, call in enumerate(self.tool_calls, start=1))


@dataclass(frozen=True, slots=True)
class CleanerPlanCandidate:
    candidate_id: str
    provider_id: str
    source_sha256: str
    plan: CleanerToolPlan


class CleanerPlanProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def generate(self, request: dict[str, Any]) -> str: ...


class CleanerInferenceService:
    """Bind one source fingerprint to one strict Qwen plan candidate."""

    def __init__(self, provider: CleanerPlanProvider) -> None:
        self._provider = provider

    def propose(
        self,
        *,
        context: dict[str, Any],
        source_sha256: str,
        case_id: str,
        source_csv: Path,
        model: str | None = None,
        raw_output_path: Path | None = None,
        max_new_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> CleanerPlanCandidate:
        _require_sha256(source_sha256)
        request = build_cleaner_runner_request(
            context,
            case_id=case_id,
            source_csv=source_csv,
            model=model,
            raw_output_path=raw_output_path,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )
        plan = parse_cleaner_tool_plan_response(self._provider.generate(request))
        identity = json.dumps(
            {
                "provider_id": self._provider.provider_id,
                "source_sha256": source_sha256.lower(),
                "plan": plan.to_dict(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return CleanerPlanCandidate(
            candidate_id=f"cleaner-candidate-{hashlib.sha256(identity).hexdigest()[:24]}",
            provider_id=self._provider.provider_id,
            source_sha256=source_sha256.lower(),
            plan=plan,
        )


def parse_cleaner_tool_plan_response(raw_response: str) -> CleanerToolPlan:
    if not isinstance(raw_response, str) or not raw_response.strip():
        raise CleanerPlanError("cleaner tool plan response must be non-empty text")
    try:
        raw = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise CleanerPlanError(f"cleaner tool plan response is not strict JSON: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise CleanerPlanError("cleaner tool plan response must be a JSON object")
    return CleanerToolPlan.from_dict(raw)


def build_cleaner_messages(
    context: dict[str, Any],
    *,
    assistant_content: str | None = None,
) -> list[dict[str, str]]:
    bounded_context = _bounded_cleaner_context(context)
    messages = [
        {"role": "system", "content": CLEANER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(scrub_cleaner_prompt_context(bounded_context), sort_keys=True),
        },
    ]
    if assistant_content is not None:
        messages.append({"role": "assistant", "content": assistant_content})
    return messages


def _bounded_cleaner_context(context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(context, dict):
        raise CleanerPlanError("cleaner context must be an object")
    version = context.get("schema_version", CLEANER_CONTEXT_VERSION)
    if version != CLEANER_CONTEXT_VERSION:
        raise CleanerPlanError(f"cleaner context schema_version must be {CLEANER_CONTEXT_VERSION}")
    supported_tools = sorted(CLEANER_TOOL_NAMES)
    supplied_tools = context.get("available_tools")
    if supplied_tools is not None and supplied_tools != supported_tools:
        raise CleanerPlanError("cleaner context available_tools must match the runtime tool vocabulary")
    return {
        **context,
        "schema_version": CLEANER_CONTEXT_VERSION,
        "available_tools": supported_tools,
    }


def build_cleaner_runner_request(
    context: dict[str, Any],
    *,
    case_id: str,
    source_csv: Path,
    model: str | None = None,
    raw_output_path: Path | None = None,
    max_new_tokens: int = 4096,
    temperature: float = 0.1,
    prompt_transport: str = "chat",
) -> dict[str, Any]:
    if prompt_transport not in {"chat", "completion"}:
        raise ValueError("prompt_transport must be chat or completion")
    if max_new_tokens <= 0:
        raise ValueError("max_new_tokens must be positive")
    if temperature < 0:
        raise ValueError("temperature must be non-negative")
    return {
        "schema_version": CLEANER_RUNNER_REQUEST_VERSION,
        "task": "propose_cleaner_tool_plan",
        "response_mode": "json",
        "prompt_transport": prompt_transport,
        "runner_options": {"max_new_tokens": max_new_tokens, "temperature": temperature},
        "model": model,
        "raw_output_path": str(raw_output_path) if raw_output_path is not None else None,
        "case_id": _required_string(case_id, "case_id"),
        "source_csv": str(source_csv),
        "messages": build_cleaner_messages(context),
    }


def scrub_cleaner_prompt_context(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: scrub_cleaner_prompt_context(item)
            for key, item in value.items()
            if not _is_path_like_prompt_key(key)
        }
    if isinstance(value, list):
        return [scrub_cleaner_prompt_context(item) for item in value]
    return value


def cleaner_completion_prompt(messages: list[dict[str, str]]) -> str:
    return "\n".join(
        [messages[0]["content"], "", "\n\n".join(message["content"] for message in messages[1:]), "", "JSON:"]
    )


def _require_exact_keys(raw: dict[str, Any], fields: frozenset[str], context: str) -> None:
    if not isinstance(raw, dict):
        raise CleanerPlanError(f"{context} must be a JSON object")
    missing = sorted(fields - set(raw))
    extra = sorted(set(raw) - fields)
    if missing:
        raise CleanerPlanError(f"{context} missing required field(s): {', '.join(missing)}")
    if extra:
        raise CleanerPlanError(f"{context} has unsupported extra field(s): {', '.join(extra)}")


def _required_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise CleanerPlanError(f"{context} must be a non-empty string")
    return value


def _optional_string(value: Any, context: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, context)


def _mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CleanerPlanError(f"{context} must be an object")
    return dict(value)


def _string_tuple(value: Any, context: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise CleanerPlanError(f"{context} must be a string list")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise CleanerPlanError(f"{context}[{index}] must be a non-empty string")
        result.append(item)
    return tuple(result)


def _is_path_like_prompt_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in PATH_LIKE_PROMPT_KEYS or normalized.endswith("_path") or normalized.endswith("_file")


def _require_sha256(value: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("source_sha256 must be a 64-character hexadecimal digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError("source_sha256 must be a 64-character hexadecimal digest") from exc
