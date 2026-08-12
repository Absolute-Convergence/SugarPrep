"""Strict typed-layout candidate contract retained for the Gemma model."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json
from typing import Any


SUPPORTED_TIME_KINDS = (
    "Index",
    "YYYY-MM-DD",
    "YyyyMmDd",
    "ISO-8601",
    "Iso8601",
    "YearMonth",
    "YearQuarter",
)
TYPED_LAYOUT_REQUIRED_FIELDS = (
    "time_col",
    "time_kind",
    "entity_col",
    "primary_value_col",
    "value_cols",
    "metadata_cols",
    "forbidden_value_cols",
)


class TypedLayoutParseError(ValueError):
    """Raised when Gemma output does not match the strict layout contract."""


@dataclass(frozen=True, slots=True)
class TypedLayoutPrediction:
    time_col: str
    time_kind: str
    entity_col: str | None
    primary_value_col: str
    value_cols: tuple[str, ...]
    metadata_cols: tuple[str, ...]
    forbidden_value_cols: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_col": self.time_col,
            "time_kind": self.time_kind,
            "entity_col": self.entity_col,
            "primary_value_col": self.primary_value_col,
            "value_cols": list(self.value_cols),
            "metadata_cols": list(self.metadata_cols),
            "forbidden_value_cols": list(self.forbidden_value_cols),
        }


def parse_typed_layout_response(
    raw_response: str,
    *,
    profile_headers: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Parse raw JSON assistant content into a validated typed layout dict."""

    if not isinstance(raw_response, str) or not raw_response.strip():
        raise TypedLayoutParseError("typed layout response must be non-empty text")
    stripped = raw_response.strip()
    if stripped.startswith("```"):
        raise TypedLayoutParseError("typed layout response must be raw JSON, not markdown")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise TypedLayoutParseError(f"typed layout response is not strict JSON: {exc.msg}") from exc
    return validate_typed_layout_payload(payload, profile_headers=profile_headers)


def parse_typed_layout_prediction(
    raw_response: str,
    *,
    profile_headers: Iterable[str] | None = None,
) -> TypedLayoutPrediction:
    return typed_layout_prediction_from_payload(
        parse_typed_layout_response(raw_response, profile_headers=profile_headers)
    )


def validate_typed_layout_payload(
    payload: Any,
    *,
    profile_headers: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate and normalize a typed layout payload without adding defaults."""

    if not isinstance(payload, dict):
        raise TypedLayoutParseError("typed layout payload must be a JSON object")
    required = set(TYPED_LAYOUT_REQUIRED_FIELDS)
    keys = set(payload)
    missing = sorted(required - keys)
    extra = sorted(keys - required)
    if missing:
        raise TypedLayoutParseError(
            f"typed layout payload missing required field(s): {', '.join(missing)}"
        )
    if extra:
        raise TypedLayoutParseError(
            f"typed layout payload has unsupported extra field(s): {', '.join(extra)}"
        )
    result: dict[str, Any] = {
        "time_col": _required_string(payload["time_col"], "time_col"),
        "time_kind": _required_time_kind(payload["time_kind"]),
        "entity_col": _optional_entity_col(payload["entity_col"]),
        "primary_value_col": _required_string(
            payload["primary_value_col"], "primary_value_col"
        ),
        "value_cols": _required_string_list(payload["value_cols"], "value_cols"),
        "metadata_cols": _string_list(payload["metadata_cols"], "metadata_cols"),
        "forbidden_value_cols": _string_list(
            payload["forbidden_value_cols"], "forbidden_value_cols"
        ),
    }
    if result["primary_value_col"] not in result["value_cols"]:
        raise TypedLayoutParseError("primary_value_col must be included in value_cols")
    forbidden_overlap = sorted(set(result["value_cols"]) & set(result["forbidden_value_cols"]))
    if forbidden_overlap:
        raise TypedLayoutParseError(
            "forbidden_value_cols must not overlap value_cols: " + ", ".join(forbidden_overlap)
        )
    _validate_profile_columns(result, profile_headers)
    return result


def typed_layout_prediction_from_payload(payload: dict[str, Any]) -> TypedLayoutPrediction:
    validated = validate_typed_layout_payload(payload)
    return TypedLayoutPrediction(
        time_col=validated["time_col"],
        time_kind=validated["time_kind"],
        entity_col=validated["entity_col"],
        primary_value_col=validated["primary_value_col"],
        value_cols=tuple(validated["value_cols"]),
        metadata_cols=tuple(validated["metadata_cols"]),
        forbidden_value_cols=tuple(validated["forbidden_value_cols"]),
    )


def _required_time_kind(value: Any) -> str:
    time_kind = _required_string(value, "time_kind")
    if time_kind not in SUPPORTED_TIME_KINDS:
        raise TypedLayoutParseError(f"time_kind is not supported: {time_kind}")
    return time_kind


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypedLayoutParseError(f"{field_name} must be a non-empty string")
    return value


def _optional_entity_col(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise TypedLayoutParseError("entity_col must be a non-empty string or null")
    return value


def _required_string_list(value: Any, field_name: str) -> list[str]:
    values = _string_list(value, field_name)
    if not values:
        raise TypedLayoutParseError(f"{field_name} must contain at least one column")
    return values


def _string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise TypedLayoutParseError(f"{field_name} must be a list of non-empty strings")
    values: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise TypedLayoutParseError(f"{field_name}[{index}] must be a non-empty string")
        if item in seen:
            raise TypedLayoutParseError(
                f"{field_name} must not contain duplicate columns: {item}"
            )
        seen.add(item)
        values.append(item)
    return values


def _validate_profile_columns(
    payload: dict[str, Any], profile_headers: Iterable[str] | None
) -> None:
    if profile_headers is None:
        return
    headers = {header for header in profile_headers if isinstance(header, str)}
    if not headers:
        return
    referenced = [
        payload["time_col"],
        payload["entity_col"],
        payload["primary_value_col"],
        *payload["value_cols"],
        *payload["metadata_cols"],
        *payload["forbidden_value_cols"],
    ]
    missing = sorted(
        {
            column
            for column in referenced
            if isinstance(column, str) and column != "row_index" and column not in headers
        }
    )
    if missing:
        raise TypedLayoutParseError(
            "typed layout references column(s) absent from profile: " + ", ".join(missing)
        )
