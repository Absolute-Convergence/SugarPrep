"""Parse declarative recipe documents without performing I/O or inference."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import yaml

from sugarprep.domain.errors import DomainValidationError
from sugarprep.domain.recipe import Layout, OutputColumn, Recipe, RowRule, TransformSpec


class RecipeDocumentError(DomainValidationError):
    """Raised when a recipe document is not a valid explicit recipe."""


_TOP_LEVEL_KEYS = frozenset({"version", "name", "input", "output", "layout", "row_rules", "reject_policy"})


def parse_recipe(document: str) -> Recipe:
    """Parse a complete recipe document; never fill missing intent."""

    if not isinstance(document, str) or not document.strip():
        raise RecipeDocumentError("recipe document must be non-empty text")
    try:
        raw = yaml.safe_load(document)
    except yaml.YAMLError as exc:
        raise RecipeDocumentError(f"recipe document is not valid YAML: {exc}") from exc
    root = _mapping(raw, "recipe")
    if "source" in root:
        raise RecipeDocumentError("recipe source paths are not supported; datasets are bound during compilation")
    unknown = sorted(set(root).difference(_TOP_LEVEL_KEYS))
    if unknown:
        raise RecipeDocumentError(f"recipe contains unsupported keys: {', '.join(unknown)}")

    input_raw = _mapping(root.get("input"), "input")
    output_raw = _mapping(root.get("output"), "output")
    layout_raw = _mapping(root.get("layout"), "layout")
    columns_raw = output_raw.get("columns")
    if not isinstance(columns_raw, list) or not columns_raw:
        raise RecipeDocumentError("output.columns must be a non-empty list")

    version = root.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int):
        raise RecipeDocumentError("version must be an integer")
    return Recipe(
        version=version,
        name=_required_string(root, "name"),
        output_columns=tuple(_parse_output_column(item) for item in columns_raw),
        layout=Layout(
            time_column=_required_string(layout_raw, "time_col"),
            time_kind=_required_string(layout_raw, "time_kind"),
            entity_column=_optional_string(layout_raw.get("entity_col"), "layout.entity_col"),
            value_columns=_string_tuple(layout_raw.get("value_cols"), "layout.value_cols", required=True),
            primary_value_column=_required_string(layout_raw, "primary_value_col"),
            missing_tokens=_string_tuple(
                layout_raw.get("missing_tokens", ("", "NA", "null", "nan", "NaN")),
                "layout.missing_tokens",
                required=False,
            ),
            missing_default=_optional_mapping(layout_raw.get("missing_default"), default={"kind": "NaN"}),
            sort_by_time=_optional_bool(layout_raw.get("sort_by_time"), default=True, context="layout.sort_by_time"),
            dedupe=_optional_string(layout_raw.get("dedupe"), "layout.dedupe") or "Error",
        ),
        expected_headers=_string_tuple(input_raw.get("expected_headers"), "input.expected_headers", required=True),
        row_rules=_parse_row_rules(root.get("row_rules")),
        reject_policy=_optional_string(root.get("reject_policy"), "reject_policy") or "fail",
    )


def _parse_output_column(raw: Any) -> OutputColumn:
    column = _mapping(raw, "output column")
    transforms_raw = column.get("transforms")
    if transforms_raw is not None and ("transform" in column or "params" in column):
        raise RecipeDocumentError("output column cannot mix transforms with transform/params")
    if transforms_raw is None:
        transforms = (
            TransformSpec(
                name=_optional_string(column.get("transform"), "output column transform") or "copy",
                parameters=_optional_mapping(column.get("params")),
            ),
        )
    else:
        if not isinstance(transforms_raw, list) or not transforms_raw:
            raise RecipeDocumentError("transforms must be a non-empty list")
        transforms = tuple(_parse_transform(item) for item in transforms_raw)
    return OutputColumn(
        name=_required_string(column, "name"),
        source=_optional_string(column.get("source"), "output column source"),
        sources=_string_tuple(column.get("sources"), "output column sources", required=False),
        generate=_optional_string(column.get("generate"), "output column generate"),
        derive=_optional_string(column.get("derive"), "output column derive"),
        derive_parameters=_optional_mapping(column.get("derive_params")),
        transforms=transforms,
    )


def _parse_transform(raw: Any) -> TransformSpec:
    transform = _mapping(raw, "transform")
    return TransformSpec(
        name=_required_string(transform, "name"),
        parameters=_optional_mapping(transform.get("params")),
    )


def _parse_row_rules(raw: Any) -> tuple[RowRule, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise RecipeDocumentError("row_rules must be a list")
    rules: list[RowRule] = []
    for item in raw:
        rule = _mapping(item, "row rule")
        rules.append(
            RowRule(
                name=_required_string(rule, "name"),
                column=_required_string(rule, "column"),
                action=_optional_string(rule.get("action"), "row rule action") or "reject",
                parameters=_optional_mapping(rule.get("params")),
            )
        )
    return tuple(rules)


def _mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecipeDocumentError(f"{context} must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise RecipeDocumentError(f"{context} keys must be strings")
    return dict(value)


def _required_string(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RecipeDocumentError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, context: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RecipeDocumentError(f"{context} must be a non-empty string when present")
    return value.strip()


def _string_tuple(value: Any, context: str, *, required: bool) -> tuple[str, ...]:
    if value is None and not required:
        return ()
    if not isinstance(value, (list, tuple)) or (required and not value):
        qualifier = "non-empty " if required else ""
        raise RecipeDocumentError(f"{context} must be a {qualifier}string list")
    if not all(isinstance(item, str) for item in value):
        raise RecipeDocumentError(f"{context} must contain only strings")
    return tuple(value)


def _optional_mapping(value: Any, *, default: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if value is None:
        return dict(default or {})
    return _mapping(value, "parameters")


def _optional_bool(value: Any, *, default: bool, context: str) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise RecipeDocumentError(f"{context} must be a boolean")
    return value
