"""Deterministic scalar transforms used by preparation plans."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Callable


DEFAULT_MISSING_TOKENS = ("", "NA", "N/A", "NULL", "null", "NaN", "nan")
DEFAULT_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%Y%m%d",
    "%B %Y",
    "%b %Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
)
NUMERIC_SUFFIXES = {
    "K": 1_000.0,
    "M": 1_000_000.0,
    "B": 1_000_000_000.0,
    "T": 1_000_000_000_000.0,
}

Transform = Callable[[str, str, Mapping[str, Any]], str]


@dataclass(frozen=True, slots=True)
class MissingValue:
    is_missing: bool
    output_value: str = ""


def apply_transform(
    name: str,
    value: str,
    column_name: str,
    parameters: Mapping[str, Any] | None = None,
) -> str:
    transform = TRANSFORMS.get(name)
    if transform is None:
        raise ValueError(f"unsupported transform {name} for {column_name}")
    resolved = parameters or {}
    missing = resolve_missing(value, resolved)
    if missing.is_missing:
        return missing.output_value
    return transform(value, column_name, resolved)


def resolve_missing(value: str, parameters: Mapping[str, Any]) -> MissingValue:
    text = (value or "").strip() if bool(parameters.get("missing_trim", True)) else value
    tokens = parameters.get("missing_tokens", DEFAULT_MISSING_TOKENS)
    if not isinstance(tokens, Sequence) or isinstance(tokens, str):
        raise ValueError("missing_tokens must be a sequence when provided")
    if text in tokens:
        return MissingValue(True, str(parameters.get("missing_output", "")))
    return MissingValue(False)


def transform_copy(value: str, _column_name: str, _parameters: Mapping[str, Any]) -> str:
    return value


def transform_trim(value: str, _column_name: str, _parameters: Mapping[str, Any]) -> str:
    return (value or "").strip()


def transform_parse_numeric(value: str, column_name: str, _parameters: Mapping[str, Any]) -> str:
    text = (value or "").strip()
    try:
        return format_number(float(text))
    except ValueError as exc:
        raise ValueError(f"{column_name} expected plain numeric value, got {value!r}") from exc


def transform_parse_flexible_number(
    value: str,
    column_name: str,
    parameters: Mapping[str, Any],
) -> str:
    text = (value or "").strip()
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()

    text = text.replace(",", "")
    for symbol in str(parameters.get("currency_symbols", "$£€¥")):
        text = text.replace(symbol, "")
    text = re.sub(r"\s+", "", text)

    percent_mode = str(parameters.get("percent", "number"))
    percent = text.endswith("%")
    if percent:
        text = text[:-1]

    multiplier = 1.0
    if bool(parameters.get("allow_suffixes", True)) and text:
        suffix = text[-1].upper()
        if suffix in NUMERIC_SUFFIXES:
            multiplier = NUMERIC_SUFFIXES[suffix]
            text = text[:-1]

    try:
        parsed = float(text) * multiplier
    except ValueError as exc:
        raise ValueError(f"{column_name} expected flexible numeric value, got {value!r}") from exc
    if negative:
        parsed *= -1
    if percent and percent_mode == "fraction":
        parsed /= 100.0
    elif percent and percent_mode != "number":
        raise ValueError(f"{column_name} has unsupported percent mode {percent_mode!r}")
    return format_number(parsed)


def transform_parse_date(value: str, column_name: str, parameters: Mapping[str, Any]) -> str:
    parsed = parse_datetime((value or "").strip(), parameters.get("formats"))
    if parsed is None:
        raise ValueError(f"{column_name} expected date/datetime value, got {value!r}")
    return parsed.strftime(str(parameters.get("output_format", "%Y-%m-%d")))


def transform_map_values(value: str, column_name: str, parameters: Mapping[str, Any]) -> str:
    mapping = parameters.get("mapping")
    if not isinstance(mapping, Mapping):
        raise ValueError(f"{column_name} map_values transform requires a mapping object")
    key = (value or "").strip() if bool(parameters.get("trim", True)) else value
    if key in mapping:
        return str(mapping[key])
    if "default" in parameters:
        return str(parameters["default"])
    if bool(parameters.get("allow_unmapped", False)):
        return key
    raise ValueError(f"{column_name} has unmapped value {value!r}")


def parse_datetime(value: str, formats: Any = None) -> datetime | None:
    if "T" in value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass

    date_formats = formats if _is_format_sequence(formats) else DEFAULT_DATE_FORMATS
    for date_format in date_formats:
        if not isinstance(date_format, str):
            continue
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    return None


def _is_format_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str) and bool(value)


def format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return format(value, ".15g")


TRANSFORMS: dict[str, Transform] = {
    "copy": transform_copy,
    "trim": transform_trim,
    "parse_numeric": transform_parse_numeric,
    "parse_flexible_number": transform_parse_flexible_number,
    "parse_date": transform_parse_date,
    "map_values": transform_map_values,
}
