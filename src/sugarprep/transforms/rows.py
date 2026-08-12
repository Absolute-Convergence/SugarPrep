"""Deterministic rules evaluated over prepared rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from sugarprep.transforms.cells import DEFAULT_MISSING_TOKENS, parse_datetime


RowRuleCheck = Callable[[str, str, Mapping[str, Any]], None]


@dataclass(frozen=True, slots=True)
class RowRuleViolation(Exception):
    rule: str
    column: str
    reason: str

    def __str__(self) -> str:
        return f"{self.column} failed {self.rule}: {self.reason}"


def check_row_rule(
    name: str,
    value: str,
    column_name: str,
    parameters: Mapping[str, Any] | None = None,
) -> None:
    rule = ROW_RULES.get(name)
    if rule is None:
        raise ValueError(f"unsupported row rule {name} for {column_name}")
    rule(value, column_name, parameters or {})


def rule_required(value: str, column_name: str, parameters: Mapping[str, Any]) -> None:
    if _is_missing(value, parameters):
        raise RowRuleViolation("required", column_name, "value is missing")


def rule_numeric_range(value: str, column_name: str, parameters: Mapping[str, Any]) -> None:
    if _is_missing(value, parameters):
        return
    number = _parse_number(value, column_name, "numeric_range")
    minimum = _optional_number(parameters.get("min"), column_name, "min")
    maximum = _optional_number(parameters.get("max"), column_name, "max")
    if minimum is not None and number < minimum:
        raise RowRuleViolation("numeric_range", column_name, f"{number:g} is below minimum {minimum:g}")
    if maximum is not None and number > maximum:
        raise RowRuleViolation("numeric_range", column_name, f"{number:g} is above maximum {maximum:g}")


def rule_nonnegative(value: str, column_name: str, parameters: Mapping[str, Any]) -> None:
    if _is_missing(value, parameters):
        return
    number = _parse_number(value, column_name, "nonnegative")
    if number < 0:
        raise RowRuleViolation("nonnegative", column_name, f"{number:g} is negative")


def rule_integer_like(value: str, column_name: str, parameters: Mapping[str, Any]) -> None:
    if _is_missing(value, parameters):
        return
    number = _parse_number(value, column_name, "integer_like")
    if not number.is_integer():
        raise RowRuleViolation("integer_like", column_name, f"{number:g} is not integer-like")


def rule_allowed_values(value: str, column_name: str, parameters: Mapping[str, Any]) -> None:
    if _is_missing(value, parameters):
        return
    values = parameters.get("values")
    if not isinstance(values, Sequence) or isinstance(values, str):
        raise ValueError(f"{column_name} allowed_values requires a scalar values sequence")
    if not all(isinstance(item, str | int | float | bool) for item in values):
        raise ValueError(f"{column_name} allowed_values requires a scalar values sequence")
    if value not in {str(item) for item in values}:
        raise RowRuleViolation("allowed_values", column_name, "value is not allowed")


def rule_date_range(value: str, column_name: str, parameters: Mapping[str, Any]) -> None:
    if _is_missing(value, parameters):
        return
    parsed = parse_datetime(value, parameters.get("formats"))
    if parsed is None:
        raise RowRuleViolation("date_range", column_name, "value is not parseable as a date")
    minimum = _optional_datetime(parameters.get("min"), parameters, column_name, "min")
    maximum = _optional_datetime(parameters.get("max"), parameters, column_name, "max")
    if minimum is not None and parsed < minimum:
        raise RowRuleViolation("date_range", column_name, f"value is before minimum {parameters.get('min')}")
    if maximum is not None and parsed > maximum:
        raise RowRuleViolation("date_range", column_name, f"value is after maximum {parameters.get('max')}")


def _is_missing(value: str, parameters: Mapping[str, Any]) -> bool:
    text = (value or "").strip() if bool(parameters.get("missing_trim", True)) else value
    tokens = parameters.get("missing_tokens", DEFAULT_MISSING_TOKENS)
    if not isinstance(tokens, Sequence) or isinstance(tokens, str):
        raise ValueError("missing_tokens must be a sequence when provided")
    return text in tokens


def _parse_number(value: str, column_name: str, rule_name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise RowRuleViolation(rule_name, column_name, "value is not numeric") from exc


def _optional_number(value: Any, column_name: str, label: str) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{column_name} {label} must be numeric") from exc


def _optional_datetime(
    value: Any,
    parameters: Mapping[str, Any],
    column_name: str,
    label: str,
) -> datetime | None:
    if value is None:
        return None
    parsed = parse_datetime(str(value), parameters.get("formats"))
    if parsed is None:
        raise ValueError(f"{column_name} {label} must be parseable as a date")
    return parsed


ROW_RULES: dict[str, RowRuleCheck] = {
    "required": rule_required,
    "numeric_range": rule_numeric_range,
    "nonnegative": rule_nonnegative,
    "integer_like": rule_integer_like,
    "allowed_values": rule_allowed_values,
    "date_range": rule_date_range,
}
