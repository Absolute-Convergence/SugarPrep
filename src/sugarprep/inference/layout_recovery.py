"""Heuristic recovery for tiny-model typed layout outputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from sugarprep.inference.layout_contract import (
    TYPED_LAYOUT_REQUIRED_FIELDS,
    TypedLayoutParseError,
    validate_typed_layout_payload,
)


OUTPUT_RECOVERY_OFF = "off"
OUTPUT_RECOVERY_HEURISTIC = "heuristic"
SUPPORTED_OUTPUT_RECOVERY_MODES = (OUTPUT_RECOVERY_OFF, OUTPUT_RECOVERY_HEURISTIC)

_ASSIGNMENT_RE = re.compile(r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_\- ]*)\s*(?:=|:)\s*(?P<value>.+?)\s*$")
_FIELD_ASSIGNMENT_RE = re.compile(
    r"(?P<key>"
    r"time_col|time_column|time_kind|entity_col|entity_column|"
    r"primary_value_col|primary_value_column|value_cols|value_columns|"
    r"required_value_columns|metadata_cols|metadata_columns|"
    r"required_metadata_columns|forbidden_value_cols|forbidden_value_columns"
    r")\s*(?:=|:)",
    re.IGNORECASE,
)

_KEY_ALIASES = {
    "time_col": "time_col",
    "time_column": "time_col",
    "time_kind": "time_kind",
    "entity_col": "entity_col",
    "entity_column": "entity_col",
    "primary_value_col": "primary_value_col",
    "primary_value_column": "primary_value_col",
    "value_cols": "value_cols",
    "value_columns": "value_cols",
    "required_value_columns": "value_cols",
    "metadata_cols": "metadata_cols",
    "metadata_columns": "metadata_cols",
    "required_metadata_columns": "metadata_cols",
    "forbidden_value_cols": "forbidden_value_cols",
    "forbidden_value_columns": "forbidden_value_cols",
}

_LIST_FIELDS = {"value_cols", "metadata_cols", "forbidden_value_cols"}
_SCALAR_FIELDS = {"time_col", "time_kind", "primary_value_col"}


class OutputRecoveryError(ValueError):
    """Raised when a non-strict model output cannot be safely recovered."""


@dataclass(frozen=True)
class RecoveredLayoutResult:
    prediction: dict[str, Any]
    strategy: str
    recovered_fields: tuple[str, ...]
    field_sources: dict[str, str]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": OUTPUT_RECOVERY_HEURISTIC,
            "strategy": self.strategy,
            "recovered_fields": list(self.recovered_fields),
            "field_sources": dict(self.field_sources),
            "warnings": list(self.warnings),
        }


def normalize_output_recovery_mode(value: str) -> str:
    if value not in SUPPORTED_OUTPUT_RECOVERY_MODES:
        raise ValueError("output_recovery must be one of: " + ", ".join(SUPPORTED_OUTPUT_RECOVERY_MODES))
    return value


def recover_typed_layout_response(
    raw_response: str,
    *,
    profile_headers: Iterable[str] | None = None,
    column_label_map: dict[str, str] | None = None,
) -> RecoveredLayoutResult:
    """Recover strict typed layout JSON from a tiny-model text response."""

    if not isinstance(raw_response, str) or not raw_response.strip():
        raise OutputRecoveryError("recovery input must be non-empty text")

    json_recovery = recover_embedded_json(
        raw_response,
        profile_headers=profile_headers,
        column_label_map=column_label_map,
    )
    if json_recovery is not None:
        return json_recovery

    payload, field_sources, warnings = recover_key_value_assignments(raw_response)
    if column_label_map:
        payload = resolve_indexed_payload(payload, column_label_map)
    payload = repair_recoverable_invariants(payload, warnings)
    missing = [field for field in TYPED_LAYOUT_REQUIRED_FIELDS if field not in payload]
    if missing:
        raise OutputRecoveryError("heuristic output recovery missing required field(s): " + ", ".join(missing))
    try:
        prediction = validate_typed_layout_payload(payload, profile_headers=profile_headers)
    except TypedLayoutParseError as exc:
        raise OutputRecoveryError(f"heuristic output recovery produced invalid payload: {exc}") from exc
    return RecoveredLayoutResult(
        prediction=prediction,
        strategy="key_value_assignments",
        recovered_fields=tuple(TYPED_LAYOUT_REQUIRED_FIELDS),
        field_sources=field_sources,
        warnings=tuple(warnings),
    )


def repair_recoverable_invariants(payload: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    repaired = dict(payload)
    primary = repaired.get("primary_value_col")
    value_cols = repaired.get("value_cols")
    if isinstance(primary, str) and isinstance(value_cols, list) and primary not in value_cols:
        repaired["value_cols"] = [primary, *value_cols]
        warnings.append("inserted primary_value_col into value_cols")
    return repaired


def resolve_indexed_payload(payload: dict[str, Any], column_label_map: dict[str, str]) -> dict[str, Any]:
    resolved = dict(payload)
    normalized_label_map = {label.upper(): column for label, column in column_label_map.items()}
    for field in ("time_col", "entity_col", "primary_value_col"):
        if field in resolved:
            resolved[field] = resolve_indexed_scalar(resolved[field], normalized_label_map, field=field)
    for field in _LIST_FIELDS:
        if field in resolved:
            resolved[field] = [
                resolve_indexed_scalar(item, normalized_label_map, field=field) for item in resolved[field]
            ]
    return resolved


def resolve_indexed_scalar(value: Any, label_map: dict[str, str], *, field: str) -> Any:
    if field == "entity_col" and isinstance(value, str) and value.lower() in {"none", "null"}:
        return None
    if not isinstance(value, str):
        return value
    token = value.upper()
    if token in label_map:
        return label_map[token]
    trimmed_token = re.sub(r"^[^A-Z0-9]+|[^A-Z0-9]+$", "", token)
    if trimmed_token in label_map:
        return label_map[trimmed_token]
    return value


def recover_embedded_json(
    raw_response: str,
    *,
    profile_headers: Iterable[str] | None,
    column_label_map: dict[str, str] | None = None,
) -> RecoveredLayoutResult | None:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", raw_response):
        try:
            candidate, _ = decoder.raw_decode(raw_response[match.start() :])
        except json.JSONDecodeError:
            continue
        payload = (
            resolve_indexed_payload(candidate, column_label_map)
            if column_label_map and isinstance(candidate, dict)
            else candidate
        )
        try:
            prediction = validate_typed_layout_payload(
                payload,
                profile_headers=profile_headers,
            )
        except TypedLayoutParseError:
            continue
        return RecoveredLayoutResult(
            prediction=prediction,
            strategy="embedded_json_object",
            recovered_fields=tuple(TYPED_LAYOUT_REQUIRED_FIELDS),
            field_sources={"json_object": raw_response[match.start() : match.start() + 120]},
        )
    return None


def recover_key_value_assignments(raw_response: str) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    for block in candidate_assignment_blocks(raw_response):
        payload, field_sources, warnings = parse_assignment_segments(block)
        if all(field in payload for field in TYPED_LAYOUT_REQUIRED_FIELDS):
            return payload, field_sources, warnings
    return parse_assignment_segments(all_assignment_segments(raw_response))


def candidate_assignment_blocks(raw_response: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in raw_response.splitlines():
        segments = assignment_segments_for_line(line)
        if len(segments) > 1:
            if current:
                blocks.append(current)
                current = []
            blocks.append(segments)
            continue
        if len(segments) == 1 and starts_with_assignment_field(line):
            current.append(segments[0])
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def all_assignment_segments(raw_response: str) -> list[str]:
    segments: list[str] = []
    for line in raw_response.splitlines():
        segments.extend(assignment_segments_for_line(line))
    return segments


def assignment_segments_for_line(line: str) -> list[str]:
    matches = list(_FIELD_ASSIGNMENT_RE.finditer(line))
    if not matches:
        return []
    segments: list[str] = []
    for index, match in enumerate(matches):
        value_start = match.end()
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        value = line[value_start:value_end].strip().strip("|;")
        if value:
            segments.append(f"{match.group('key')} = {value}")
    return segments


def starts_with_assignment_field(line: str) -> bool:
    return _FIELD_ASSIGNMENT_RE.match(line.strip()) is not None


def parse_assignment_segments(segments: list[str]) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    payload: dict[str, Any] = {}
    field_sources: dict[str, str] = {}
    seen_values: dict[str, list[Any]] = {}
    warnings: list[str] = []
    for line in segments:
        match = _ASSIGNMENT_RE.match(line)
        if match is None:
            continue
        field = canonical_field_name(match.group("key"))
        if field is None:
            continue
        value = parse_field_value(field, match.group("value"))
        if field not in payload:
            payload[field] = value
            field_sources[field] = line.strip()
        seen_values.setdefault(field, []).append(value)

    for field, values in seen_values.items():
        unique = unique_json_values(values)
        if len(unique) > 1:
            warnings.append(f"conflicting repeated assignments for {field}; kept first value")
    return payload, field_sources, warnings


def canonical_field_name(value: str) -> str | None:
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", value.strip().lower()).strip("_")
    return _KEY_ALIASES.get(normalized)


def parse_field_value(field: str, value: str) -> Any:
    cleaned = value.strip().rstrip(",")
    if field in _LIST_FIELDS:
        return parse_list_value(cleaned)
    if field == "entity_col":
        scalar = parse_scalar_value(cleaned)
        return None if scalar.lower() in {"null", "none"} else scalar
    if field in _SCALAR_FIELDS:
        return parse_scalar_value(cleaned)
    raise OutputRecoveryError(f"unsupported recovery field: {field}")


def parse_scalar_value(value: str) -> str:
    stripped = strip_wrapping_quotes(strip_inline_annotation(value).strip().rstrip("."))
    if not stripped:
        raise OutputRecoveryError("recovered scalar field is empty")
    return stripped


def strip_inline_annotation(value: str) -> str:
    stripped = value.strip()
    for marker in (
        "<output truncated>",
        "<|im_end|>",
        "<end_of_turn>",
        "<|eot_id|>",
        "<Column label table:",
        "Column label table:",
        "Rules:",
        "Direct indexed field-plan:",
        "Return exactly",
        "Use labels from",
        "No JSON.",
        "<---",
        "<--",
        " #",
        " //",
    ):
        index = stripped.find(marker)
        if index != -1:
            return stripped[:index].strip()
    return stripped


def parse_list_value(value: str) -> list[str]:
    stripped = strip_inline_annotation(value.strip())
    if stripped == "[]":
        return []
    if stripped.startswith("[") and stripped.endswith("]"):
        inner = stripped[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar_value(part) for part in split_list_items(inner)]
    if "," in stripped:
        return [parse_scalar_value(part) for part in split_list_items(stripped)]
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return [parse_scalar_value(stripped)]
    if not isinstance(parsed, list):
        raise OutputRecoveryError("recovered list field is not a list")
    return [parse_scalar_value(str(item)) for item in parsed]


def split_list_items(value: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for char in value:
        if char in {"'", '"'}:
            quote = None if quote == char else char if quote is None else quote
            current.append(char)
            continue
        if char == "," and quote is None:
            items.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current or value.endswith(","):
        items.append("".join(current).strip())
    return [item for item in items if item]


def strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def unique_json_values(values: list[Any]) -> list[Any]:
    unique: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = json.dumps(value, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique
