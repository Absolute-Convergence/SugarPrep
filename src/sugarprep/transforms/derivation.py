"""Deterministic multi-source output-column derivations."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Callable


Derivation = Callable[[Mapping[str, str], str, Mapping[str, Any]], str]


def derive_value(
    name: str,
    source_values: Mapping[str, str],
    column_name: str,
    parameters: Mapping[str, Any] | None = None,
) -> str:
    derivation = DERIVATIONS.get(name)
    if derivation is None:
        raise ValueError(f"unsupported derivation {name} for {column_name}")
    return derivation(source_values, column_name, parameters or {})


def derive_join(
    source_values: Mapping[str, str],
    _column_name: str,
    parameters: Mapping[str, Any],
) -> str:
    return str(parameters.get("separator", "")).join(source_values.values())


def derive_template(
    source_values: Mapping[str, str],
    column_name: str,
    parameters: Mapping[str, Any],
) -> str:
    template = parameters.get("template")
    if not isinstance(template, str) or not template:
        raise ValueError(f"{column_name} template derivation requires non-empty template")
    try:
        return template.format_map(source_values)
    except KeyError as exc:
        raise ValueError(f"{column_name} template references unknown source {exc.args[0]!r}") from exc


def derive_datetime_parts(
    source_values: Mapping[str, str],
    column_name: str,
    parameters: Mapping[str, Any],
) -> str:
    parts = {
        "year": _resolve_int_part("year", source_values, parameters, column_name),
        "month": _resolve_int_part("month", source_values, parameters, column_name),
        "day": _resolve_int_part("day", source_values, parameters, column_name),
        "hour": _resolve_int_part("hour", source_values, parameters, column_name, default=0),
        "minute": _resolve_int_part("minute", source_values, parameters, column_name, default=0),
        "second": _resolve_int_part("second", source_values, parameters, column_name, default=0),
    }
    try:
        value = datetime(**parts)
    except ValueError as exc:
        raise ValueError(f"{column_name} has invalid datetime parts: {exc}") from exc
    return value.strftime(str(parameters.get("output_format", "%Y-%m-%dT%H:%M:%S")))


def _resolve_int_part(
    part_name: str,
    source_values: Mapping[str, str],
    parameters: Mapping[str, Any],
    column_name: str,
    default: int | None = None,
) -> int:
    raw_part = parameters.get(part_name, default)
    if raw_part is None:
        raise ValueError(f"{column_name} datetime_parts missing {part_name}")
    if isinstance(raw_part, int):
        return raw_part
    if isinstance(raw_part, str) and raw_part in source_values:
        raw_part = source_values[raw_part]
    try:
        return int(str(raw_part).strip())
    except ValueError as exc:
        raise ValueError(
            f"{column_name} datetime_parts {part_name} is not an integer: {raw_part!r}"
        ) from exc


DERIVATIONS: dict[str, Derivation] = {
    "join": derive_join,
    "template": derive_template,
    "datetime_parts": derive_datetime_parts,
}
