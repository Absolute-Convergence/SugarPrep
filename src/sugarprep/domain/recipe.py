"""Declarative preparation recipe contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from sugarprep.domain.errors import DomainValidationError


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise DomainValidationError(f"recipe parameter value has unsupported type: {type(value).__name__}")


def _frozen_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen = _freeze(value)
    if not isinstance(frozen, Mapping):
        raise DomainValidationError("parameters must be a mapping")
    return frozen


@dataclass(frozen=True, slots=True)
class TransformSpec:
    name: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required_text(self.name, "transform name"))
        object.__setattr__(self, "parameters", _frozen_mapping(self.parameters))


@dataclass(frozen=True, slots=True)
class OutputColumn:
    name: str
    source: str | None = None
    sources: tuple[str, ...] = ()
    generate: str | None = None
    derive: str | None = None
    derive_parameters: Mapping[str, Any] = field(default_factory=dict)
    transforms: tuple[TransformSpec, ...] = field(default_factory=lambda: (TransformSpec(name="copy"),))

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required_text(self.name, "output column name"))
        source = _required_text(self.source, "source") if self.source is not None else None
        sources = tuple(_required_text(value, "source") for value in self.sources)
        generate = _required_text(self.generate, "generate") if self.generate is not None else None
        if sum(bool(value) for value in (source, sources, generate)) != 1:
            raise DomainValidationError(
                f"output column {self.name} must define exactly one of source, sources, or generate"
            )
        if len(sources) != len(set(sources)):
            raise DomainValidationError(f"output column {self.name} sources must be unique")
        derive = _required_text(self.derive, "derive") if self.derive is not None else None
        if sources and derive is None:
            raise DomainValidationError(f"output column {self.name} requires derive when sources are used")
        if derive is not None and not sources:
            raise DomainValidationError(f"output column {self.name} cannot derive without sources")
        transforms = tuple(self.transforms)
        if not transforms or not all(isinstance(step, TransformSpec) for step in transforms):
            raise DomainValidationError(f"output column {self.name} requires transform specifications")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "sources", sources)
        object.__setattr__(self, "generate", generate)
        object.__setattr__(self, "derive", derive)
        object.__setattr__(self, "derive_parameters", _frozen_mapping(self.derive_parameters))
        object.__setattr__(self, "transforms", transforms)


@dataclass(frozen=True, slots=True)
class Layout:
    time_column: str
    time_kind: str
    value_columns: tuple[str, ...]
    primary_value_column: str
    entity_column: str | None = None
    missing_tokens: tuple[str, ...] = ("", "NA", "null", "nan", "NaN")
    missing_default: Mapping[str, Any] = field(default_factory=lambda: {"kind": "NaN"})
    sort_by_time: bool = True
    dedupe: str = "Error"

    def __post_init__(self) -> None:
        object.__setattr__(self, "time_column", _required_text(self.time_column, "time_column"))
        object.__setattr__(self, "time_kind", _required_text(self.time_kind, "time_kind"))
        value_columns = tuple(_required_text(value, "value_column") for value in self.value_columns)
        if not value_columns or len(value_columns) != len(set(value_columns)):
            raise DomainValidationError("value_columns must be non-empty and unique")
        primary = _required_text(self.primary_value_column, "primary_value_column")
        if primary not in value_columns:
            raise DomainValidationError("primary_value_column must be included in value_columns")
        entity = _required_text(self.entity_column, "entity_column") if self.entity_column is not None else None
        object.__setattr__(self, "value_columns", value_columns)
        object.__setattr__(self, "primary_value_column", primary)
        object.__setattr__(self, "entity_column", entity)
        object.__setattr__(self, "missing_tokens", tuple(str(value) for value in self.missing_tokens))
        object.__setattr__(self, "missing_default", _frozen_mapping(self.missing_default))
        object.__setattr__(self, "dedupe", _required_text(self.dedupe, "dedupe"))


@dataclass(frozen=True, slots=True)
class RowRule:
    name: str
    column: str
    action: str = "reject"
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required_text(self.name, "row rule name"))
        object.__setattr__(self, "column", _required_text(self.column, "row rule column"))
        object.__setattr__(self, "action", _required_text(self.action, "row rule action"))
        object.__setattr__(self, "parameters", _frozen_mapping(self.parameters))


@dataclass(frozen=True, slots=True)
class Recipe:
    version: int
    name: str
    output_columns: tuple[OutputColumn, ...]
    layout: Layout
    expected_headers: tuple[str, ...] = ()
    row_rules: tuple[RowRule, ...] = ()
    reject_policy: str = "fail"

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise DomainValidationError("recipe version must be a positive integer")
        object.__setattr__(self, "name", _required_text(self.name, "recipe name"))
        output_columns = tuple(self.output_columns)
        if not output_columns:
            raise DomainValidationError("recipe output_columns must not be empty")
        output_names = tuple(column.name for column in output_columns)
        if len(output_names) != len(set(output_names)):
            raise DomainValidationError("recipe output column names must be unique")
        layout_columns = {
            self.layout.time_column,
            self.layout.primary_value_column,
            *self.layout.value_columns,
        }
        if self.layout.entity_column is not None:
            layout_columns.add(self.layout.entity_column)
        missing_layout_columns = sorted(layout_columns.difference(output_names))
        if missing_layout_columns:
            raise DomainValidationError(
                f"layout references missing output columns: {', '.join(missing_layout_columns)}"
            )
        row_rules = tuple(self.row_rules)
        missing_rule_columns = sorted({rule.column for rule in row_rules}.difference(output_names))
        if missing_rule_columns:
            raise DomainValidationError(
                f"row rules reference missing output columns: {', '.join(missing_rule_columns)}"
            )
        object.__setattr__(self, "output_columns", output_columns)
        expected_headers = tuple(_required_text(header, "expected_header") for header in self.expected_headers)
        if len(expected_headers) != len(set(expected_headers)):
            raise DomainValidationError("expected_headers must be unique and ordered")
        object.__setattr__(self, "expected_headers", expected_headers)
        object.__setattr__(self, "row_rules", row_rules)
        object.__setattr__(self, "reject_policy", _required_text(self.reject_policy, "reject_policy"))
