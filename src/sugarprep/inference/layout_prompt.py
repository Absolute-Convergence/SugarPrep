"""Exact indexed-completion prompt used by the promoted Gemma layout model."""

from __future__ import annotations

import copy
import json
from typing import Any

from sugarprep.inference.layout_contract import (
    SUPPORTED_TIME_KINDS,
    TYPED_LAYOUT_REQUIRED_FIELDS,
)


TYPED_LAYOUT_SCHEMA_VERSION = "sugarprep.typed_layout.v1"
SUBMIT_TYPED_LAYOUT_TOOL_NAME = "submit_typed_layout"
SYSTEM_PROMPT_INDEXED = (
    "You are SugarPrep's semantic layout planner. Return exactly seven indexed "
    "assignment lines for the requested typed layout. Do not return JSON, "
    "markdown, prose, comments, code, transforms, or extra keys. SugarPrep will "
    "map labels back to columns and validate the proposal deterministically."
)


def build_indexed_layout_messages(
    profile: dict[str, Any],
    guidance: dict[str, Any] | None = None,
    *,
    max_columns: int = 64,
    max_examples_per_column: int = 3,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT_INDEXED},
        {
            "role": "user",
            "content": render_indexed_layout_user_prompt(
                profile,
                guidance or {},
                response_mode="json",
                max_columns=max_columns,
                max_examples_per_column=max_examples_per_column,
            ),
        },
    ]

def render_indexed_layout_user_prompt(
    profile: dict[str, Any],
    guidance: dict[str, Any] | None = None,
    *,
    response_mode: str = "json",
    max_columns: int = 64,
    max_examples_per_column: int = 3,
) -> str:
    """Render a tiny-model prompt that uses compact column labels."""

    context = compact_prompt_context(
        profile,
        guidance or {},
        max_columns=max_columns,
        max_examples_per_column=max_examples_per_column,
    )
    profile_context = context["profile"]
    field_plan = explicit_layout_field_plan(guidance or {}, profile_context)
    label_map = indexed_column_label_map(profile_context)
    inverse = {column: label for label, column in label_map.items()}
    indexed_plan = indexed_layout_field_plan(field_plan, inverse)
    if response_mode != "json":
        raise ValueError("indexed Gemma path supports assignment output only")
    response_instruction = (
        "Return only assignment lines. Do not return JSON, markdown, prose, comments, or schema text."
    )
    return "\n".join(
        [
            "Task: fill one SugarPrep indexed layout assignment block.",
            response_instruction,
            "This is the tiny-model indexed prompt. Use labels from the label table, not raw column names.",
            "SugarPrep will map labels back to real columns and validate the strict typed layout.",
            "Output exactly these seven assignment lines in this order:",
            "time_col =",
            "time_kind =",
            "entity_col =",
            "primary_value_col =",
            "value_cols =",
            "metadata_cols =",
            "forbidden_value_cols =",
            "Rules:",
            "1. Use none for entity_col when there is no entity axis.",
            "2. Use comma-separated labels for value_cols, metadata_cols, and forbidden_value_cols.",
            "3. Use time_kind text directly, not a label.",
            "4. Do not output examples, explanations, JSON, or repeated instructions.",
            "Direct indexed field plan:",
            *render_indexed_assignment_lines(indexed_plan),
            "Column label table:",
            *render_indexed_column_label_lines(profile_context, label_map),
            "Allowed time kinds = " + display_list(SUPPORTED_TIME_KINDS),
        ]
    )

def indexed_column_label_map(profile_context: dict[str, Any]) -> dict[str, str]:
    """Return deterministic compact labels for visible profile columns."""

    headers = _string_list(profile_context.get("headers"))
    time_candidates = set(_string_list(profile_context.get("time_axis_candidates")))
    value_candidates = set(_string_list(profile_context.get("value_column_candidates")))
    label_map: dict[str, str] = {}
    counters = {"T": 0, "V": 0, "M": 0}
    for header in headers:
        prefix = "T" if header in time_candidates else "V" if header in value_candidates else "M"
        counters[prefix] += 1
        label_map[f"{prefix}{counters[prefix]}"] = header
    return label_map

def indexed_layout_field_plan(field_plan: dict[str, Any], inverse_label_map: dict[str, str]) -> dict[str, Any]:
    return {
        "time_col": label_for_plan_value(field_plan.get("time_col"), inverse_label_map),
        "time_kind": field_plan.get("time_kind"),
        "entity_col": label_for_plan_value(field_plan.get("entity_col"), inverse_label_map, none_text="none"),
        "primary_value_col": label_for_plan_value(field_plan.get("primary_value_col"), inverse_label_map),
        "value_cols": labels_for_plan_values(field_plan.get("value_cols"), inverse_label_map),
        "metadata_cols": labels_for_plan_values(field_plan.get("metadata_cols"), inverse_label_map),
        "forbidden_value_cols": labels_for_plan_values(field_plan.get("forbidden_value_cols"), inverse_label_map),
    }

def label_for_plan_value(
    value: Any, inverse_label_map: dict[str, str], *, none_text: str = "<unspecified>"
) -> str | None:
    if value is None:
        return none_text
    if not isinstance(value, str) or not value:
        return None
    return inverse_label_map.get(value, value)

def labels_for_plan_values(value: Any, inverse_label_map: dict[str, str]) -> list[str]:
    return [inverse_label_map.get(item, item) for item in _string_list(value)]

def render_indexed_column_label_lines(profile_context: dict[str, Any], label_map: dict[str, str]) -> list[str]:
    columns_by_name = {
        raw.get("name"): raw
        for raw in profile_context.get("columns", [])
        if isinstance(raw, dict) and isinstance(raw.get("name"), str)
    }
    lines: list[str] = []
    for label, column in label_map.items():
        raw = columns_by_name.get(column, {})
        lines.append(
            f"{label} = {column}"
            + " | value_candidate="
            + bool_token(raw.get("sugarbot_value_candidate"))
            + " | likely_date_axis="
            + bool_token(raw.get("likely_date_axis"))
            + " | examples="
            + display_list(raw.get("distinct_examples"))
        )
    return lines or ["- no labels supplied"]

def render_indexed_layout_target_text(target: dict[str, Any], label_map: dict[str, str]) -> str:
    inverse = {column: label for label, column in label_map.items()}
    indexed_target = indexed_layout_field_plan(target, inverse)
    return "\n".join(render_indexed_assignment_lines(indexed_target))

def render_indexed_assignment_lines(field_plan: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for field in TYPED_LAYOUT_REQUIRED_FIELDS:
        value = field_plan.get(field)
        if field in {"value_cols", "metadata_cols", "forbidden_value_cols"}:
            lines.append(f"{field} = {display_indexed_list(value)}")
        else:
            lines.append(
                f"{field} = {display_plan_value(value, null_text='none' if field == 'entity_col' else '<unspecified>')}"
            )
    return lines

def display_indexed_list(value: Any) -> str:
    values = [str(item) for item in value] if isinstance(value, list | tuple) else []
    return ",".join(values) if values else "[]"

def compact_prompt_context(
    profile: dict[str, Any],
    guidance: dict[str, Any] | None = None,
    *,
    max_columns: int = 64,
    max_examples_per_column: int = 3,
) -> dict[str, Any]:
    """Return a bounded, JSON-shaped profile and guidance context."""

    if max_columns <= 0:
        raise ValueError("max_columns must be positive")
    if max_examples_per_column < 0:
        raise ValueError("max_examples_per_column must be non-negative")

    headers = _string_list(profile.get("headers"))
    columns = _column_contexts(profile.get("columns"), max_columns, max_examples_per_column)
    visible_headers = headers[:max_columns]
    return {
        "schema_version": TYPED_LAYOUT_SCHEMA_VERSION,
        "profile": {
            "source_path": _optional_string(profile.get("source_path")),
            "source_sha256": _optional_string(profile.get("source_sha256")),
            "profile_mode": _optional_string(profile.get("profile_mode")),
            "row_count": profile.get("row_count"),
            "profiled_row_count": profile.get("profiled_row_count"),
            "source_row_count": profile.get("source_row_count"),
            "headers": visible_headers,
            "omitted_header_count": max(0, len(headers) - len(visible_headers)),
            "value_column_candidates": _bounded_string_list(profile.get("value_column_candidates"), max_columns),
            "time_axis_candidates": _bounded_string_list(profile.get("time_axis_candidates"), max_columns),
            "generated_index_recommended": bool(profile.get("generated_index_recommended", False)),
            "columns": columns,
            "omitted_column_count": _omitted_count(profile.get("columns"), len(columns)),
        },
        "guidance": _json_ready(guidance or {}),
        "constraints": {
            "allowed_time_kinds": list(SUPPORTED_TIME_KINDS),
            "generated_time_col": "row_index",
            "output_schema": TYPED_LAYOUT_SCHEMA_VERSION,
            "allowed_tool": SUBMIT_TYPED_LAYOUT_TOOL_NAME,
            "arbitrary_transforms_allowed": False,
            "executable_code_allowed": False,
        },
    }

def explicit_layout_field_plan(guidance: dict[str, Any], profile_context: dict[str, Any]) -> dict[str, Any]:
    """Extract direct layout instructions from guidance into typed-layout fields."""

    semantic_guidance = dict_or_empty(guidance.get("guidance"))
    expected = dict_or_empty(guidance.get("expected"))
    axis_intent = dict_or_empty(semantic_guidance.get("axis_intent"))
    value_intent = dict_or_empty(semantic_guidance.get("value_intent"))
    metadata_policy = dict_or_empty(semantic_guidance.get("metadata_policy"))
    time_intent = dict_or_empty(axis_intent.get("time"))
    entity_intent = dict_or_empty(axis_intent.get("entity"))

    primary_value_col = first_string(
        expected.get("primary_value_col"),
        value_intent.get("primary"),
        metadata_policy.get("primary"),
    )
    value_cols = first_nonempty_string_list(
        expected.get("required_value_columns"),
        expected.get("value_cols"),
        value_intent.get("include"),
    )
    if primary_value_col is not None and primary_value_col not in value_cols:
        value_cols = [primary_value_col, *value_cols]

    metadata_cols = first_nonempty_string_list(
        expected.get("required_metadata_columns"),
        expected.get("metadata_cols"),
        metadata_policy.get("preserve"),
    )
    if not metadata_cols:
        metadata_cols = _string_list(metadata_policy.get("include"))

    return {
        "time_col": first_string(
            expected.get("time_col"),
            time_intent.get("column"),
            first_item(profile_context.get("time_axis_candidates")),
            "row_index" if profile_context.get("generated_index_recommended") is True else None,
        ),
        "time_kind": first_string(expected.get("time_kind"), time_intent.get("kind")),
        "entity_col": first_string(expected.get("entity_col"), entity_intent.get("column")),
        "primary_value_col": primary_value_col,
        "value_cols": value_cols,
        "metadata_cols": metadata_cols,
        "forbidden_value_cols": first_nonempty_string_list(
            expected.get("forbidden_value_columns"),
            expected.get("forbidden_value_cols"),
            value_intent.get("exclude"),
        ),
    }

def display_plan_value(value: Any, *, null_text: str = "<unspecified>") -> str:
    if value is None:
        return null_text
    if isinstance(value, list | tuple):
        return display_list(value)
    return str(value)

def display_scalar(value: Any) -> str:
    if value is None:
        return "<unknown>"
    return str(value)

def display_list(value: Any) -> str:
    values = [str(item) for item in value] if isinstance(value, list | tuple) else []
    return "[" + ", ".join(values) + "]" if values else "[]"

def bool_token(value: Any) -> str:
    return "yes" if value is True else "no"

def first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None

def first_item(value: Any) -> Any:
    if isinstance(value, list | tuple) and value:
        return value[0]
    return None

def first_nonempty_string_list(*values: Any) -> list[str]:
    for value in values:
        strings = _string_list(value)
        if strings:
            return strings
    return []

def dict_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}

def _column_contexts(raw_columns: Any, max_columns: int, max_examples_per_column: int) -> list[dict[str, Any]]:
    if not isinstance(raw_columns, list):
        return []
    contexts: list[dict[str, Any]] = []
    for raw in raw_columns[:max_columns]:
        if not isinstance(raw, dict):
            continue
        contexts.append(
            {
                "name": _optional_string(raw.get("name")),
                "missing_rate": raw.get("missing_rate"),
                "non_missing_count": raw.get("non_missing_count"),
                "numeric_success_count": raw.get("numeric_success_count"),
                "numeric_failure_count": raw.get("numeric_failure_count"),
                "integer_like_count": raw.get("integer_like_count"),
                "date_like_count": raw.get("date_like_count"),
                "sugarbot_value_candidate": bool(raw.get("sugarbot_value_candidate", False)),
                "likely_integer": bool(raw.get("likely_integer", False)),
                "likely_date_axis": bool(raw.get("likely_date_axis", False)),
                "distinct_examples": _bounded_string_list(
                    raw.get("distinct_examples"),
                    max_examples_per_column,
                ),
                "numeric_failure_examples": _bounded_string_list(
                    raw.get("numeric_failure_examples"),
                    max_examples_per_column,
                ),
            }
        )
    return contexts

def _omitted_count(raw_values: Any, visible_count: int) -> int:
    if not isinstance(raw_values, list):
        return 0
    return max(0, len(raw_values) - visible_count)

def _bounded_string_list(raw_values: Any, limit: int) -> list[str]:
    return _string_list(raw_values)[:limit]

def _string_list(raw_values: Any) -> list[str]:
    if not isinstance(raw_values, list | tuple):
        return []
    return [value for value in raw_values if isinstance(value, str)]

def _optional_string(raw_value: Any) -> str | None:
    return raw_value if isinstance(raw_value, str) else None

def _json_ready(value: Any) -> Any:
    try:
        copy.deepcopy(value)
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value
