"""Gemma indexed-completion request, recovery, and candidate binding."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from sugarprep.inference.layout_contract import (
    TypedLayoutParseError,
    TypedLayoutPrediction,
    parse_typed_layout_prediction,
    typed_layout_prediction_from_payload,
)
from sugarprep.inference.layout_prompt import (
    TYPED_LAYOUT_SCHEMA_VERSION,
    build_indexed_layout_messages,
    compact_prompt_context,
    indexed_column_label_map,
)
from sugarprep.inference.layout_recovery import (
    OutputRecoveryError,
    recover_typed_layout_response,
)


LAYOUT_RUNNER_REQUEST_VERSION = "sugarprep.unsloth_runner_request.v1"


class LayoutInferenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LayoutCandidate:
    candidate_id: str
    provider_id: str
    source_sha256: str
    prediction: TypedLayoutPrediction
    raw_response: str
    recovery: dict[str, Any] | None = None


class IndexedLayoutProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def generate(self, request: dict[str, Any]) -> str: ...


class LayoutInferenceService:
    """Run only the promoted Gemma indexed-completion contract."""

    def __init__(self, provider: IndexedLayoutProvider) -> None:
        self._provider = provider

    def propose(
        self,
        *,
        profile: dict[str, Any],
        guidance: dict[str, Any],
        source_sha256: str,
        model: str | None = None,
        raw_output_path: Path | None = None,
        max_new_tokens: int | None = None,
        temperature: float | None = None,
        max_columns: int = 64,
        max_examples_per_column: int = 3,
    ) -> LayoutCandidate:
        _require_sha256(source_sha256)
        request = build_indexed_layout_request(
            profile,
            guidance,
            model=model,
            raw_output_path=raw_output_path,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            max_columns=max_columns,
            max_examples_per_column=max_examples_per_column,
        )
        raw_response = self._provider.generate(request)
        headers = tuple(request["profile_headers"])
        recovery: dict[str, Any] | None = None
        try:
            prediction = parse_typed_layout_prediction(raw_response, profile_headers=headers)
        except TypedLayoutParseError as parse_error:
            try:
                recovered = recover_typed_layout_response(
                    raw_response,
                    profile_headers=headers,
                    column_label_map=dict(request["column_label_map"]),
                )
            except OutputRecoveryError as recovery_error:
                raise LayoutInferenceError(
                    f"{parse_error}; output recovery failed: {recovery_error}"
                ) from recovery_error
            prediction = typed_layout_prediction_from_payload(recovered.prediction)
            recovery = {**recovered.to_dict(), "parse_error": str(parse_error)}
        identity = json.dumps(
            {
                "provider_id": self._provider.provider_id,
                "source_sha256": source_sha256.lower(),
                "prediction": prediction.to_dict(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return LayoutCandidate(
            candidate_id=f"layout-candidate-{hashlib.sha256(identity).hexdigest()[:24]}",
            provider_id=self._provider.provider_id,
            source_sha256=source_sha256.lower(),
            prediction=prediction,
            raw_response=raw_response,
            recovery=recovery,
        )


def build_indexed_layout_request(
    profile: dict[str, Any],
    guidance: dict[str, Any],
    *,
    model: str | None = None,
    raw_output_path: Path | None = None,
    max_new_tokens: int | None = None,
    temperature: float | None = None,
    max_columns: int = 64,
    max_examples_per_column: int = 3,
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if max_new_tokens is not None:
        if max_new_tokens <= 0:
            raise ValueError("max_new_tokens must be positive")
        options["max_new_tokens"] = max_new_tokens
    if temperature is not None:
        if temperature < 0:
            raise ValueError("temperature must be non-negative")
        options["temperature"] = temperature
    context = compact_prompt_context(
        profile,
        {},
        max_columns=max_columns,
        max_examples_per_column=max_examples_per_column,
    )
    return {
        "schema_version": LAYOUT_RUNNER_REQUEST_VERSION,
        "task": "propose_typed_layout",
        "prompt_schema_version": TYPED_LAYOUT_SCHEMA_VERSION,
        "response_mode": "json",
        "prompt_style": "indexed",
        "prompt_transport": "completion",
        "runner_options": options,
        "model": model,
        "raw_output_path": str(raw_output_path) if raw_output_path is not None else None,
        "profile_headers": _profile_headers(profile),
        "column_label_map": indexed_column_label_map(context["profile"]),
        "messages": build_indexed_layout_messages(
            profile,
            guidance,
            max_columns=max_columns,
            max_examples_per_column=max_examples_per_column,
        ),
    }


def indexed_completion_prompt(messages: list[dict[str, str]]) -> str:
    if len(messages) < 2 or messages[0].get("role") != "system":
        raise LayoutInferenceError("layout request must contain system and user messages")
    content = "\n\n".join(message["content"] for message in messages[1:])
    marker = "\nRequired output schema:\n"
    index = content.find(marker)
    if index != -1:
        content = content[:index].rstrip()
    assignment_contract = [
        "Return exactly seven assignment lines in this order:",
        "time_col =",
        "time_kind =",
        "entity_col =",
        "primary_value_col =",
        "value_cols =",
        "metadata_cols =",
        "forbidden_value_cols =",
        "Use labels from the label table for column fields.",
        "Use none for entity_col when there is no entity axis.",
        "Use comma-separated labels for list fields.",
        "No JSON. No markdown. No prose. No schema. No comments. No repeated instructions.",
    ]
    return "\n".join(
        [
            "You are completing one machine-readable SugarPrep indexed layout assignment block.",
            "Ignore chat roles. Do not answer with instructions.",
            "",
            content,
            "",
            "Copy direct indexed field-plan labels when present.",
            *assignment_contract,
            "Start the next line with time_col = and stop after forbidden_value_cols.",
            "ASSIGNMENTS:",
        ]
    )


def _profile_headers(profile: dict[str, Any]) -> list[str]:
    headers = profile.get("headers")
    if not isinstance(headers, (list, tuple)):
        return []
    return [header for header in headers if isinstance(header, str)]


def _require_sha256(value: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("source_sha256 must be a 64-character hexadecimal digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError("source_sha256 must be a 64-character hexadecimal digest") from exc
