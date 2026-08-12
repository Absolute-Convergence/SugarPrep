"""Compile explicit recipes and profile evidence into preparation plans."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from sugarprep.domain.errors import DomainValidationError
from sugarprep.domain.plan import PreparationPlan
from sugarprep.domain.profile import DatasetProfile
from sugarprep.domain.recipe import Recipe


class PlanCompilationError(DomainValidationError):
    """Raised when an explicit recipe cannot compile against profile evidence."""


@dataclass(frozen=True, slots=True)
class CompilationPolicy:
    transforms: frozenset[str]
    derivations: frozenset[str]
    generators: frozenset[str]
    time_kinds: frozenset[str]
    row_rules: frozenset[str]
    row_rule_actions: frozenset[str]
    reject_policies: frozenset[str]


DEFAULT_COMPILATION_POLICY = CompilationPolicy(
    transforms=frozenset({"copy", "trim", "parse_numeric", "parse_flexible_number", "parse_date", "map_values"}),
    derivations=frozenset({"join", "template", "datetime_parts"}),
    generators=frozenset({"row_index"}),
    time_kinds=frozenset({"Index", "YYYY-MM-DD", "YyyyMmDd", "ISO-8601", "Iso8601", "YearMonth", "YearQuarter"}),
    row_rules=frozenset({"required", "numeric_range", "nonnegative", "integer_like", "allowed_values", "date_range"}),
    row_rule_actions=frozenset({"reject", "warn"}),
    reject_policies=frozenset({"fail", "drop"}),
)


def compile_recipe(
    recipe: Recipe,
    profile: DatasetProfile,
    *,
    policy: CompilationPolicy = DEFAULT_COMPILATION_POLICY,
) -> PreparationPlan:
    """Bind a complete recipe to one exact profiled snapshot."""

    actual_headers = profile.snapshot.headers
    if recipe.expected_headers and recipe.expected_headers != actual_headers:
        raise PlanCompilationError("recipe expected_headers do not match the profiled snapshot")
    source_headers = set(actual_headers)

    for column in recipe.output_columns:
        if column.source is not None and column.source not in source_headers:
            raise PlanCompilationError(
                f"output column {column.name} references unknown source column {column.source}"
            )
        missing_sources = sorted(set(column.sources).difference(source_headers))
        if missing_sources:
            raise PlanCompilationError(
                f"output column {column.name} references unknown source columns: {', '.join(missing_sources)}"
            )
        if column.generate is not None and column.generate not in policy.generators:
            raise PlanCompilationError(f"output column {column.name} uses unsupported generator {column.generate}")
        if column.derive is not None and column.derive not in policy.derivations:
            raise PlanCompilationError(f"output column {column.name} uses unsupported derivation {column.derive}")
        for transform in column.transforms:
            if transform.name not in policy.transforms:
                raise PlanCompilationError(
                    f"output column {column.name} uses unsupported transform {transform.name}"
                )

    if recipe.layout.time_kind not in policy.time_kinds:
        raise PlanCompilationError(f"unsupported layout time_kind: {recipe.layout.time_kind}")
    for rule in recipe.row_rules:
        if rule.name not in policy.row_rules:
            raise PlanCompilationError(f"unsupported row rule: {rule.name}")
        if rule.action not in policy.row_rule_actions:
            raise PlanCompilationError(f"unsupported row rule action: {rule.action}")
    if recipe.reject_policy not in policy.reject_policies:
        raise PlanCompilationError(f"unsupported reject_policy: {recipe.reject_policy}")

    return PreparationPlan(
        plan_id=_plan_id(recipe, profile),
        version=recipe.version,
        recipe_name=recipe.name,
        input_snapshot=profile.snapshot,
        output_columns=recipe.output_columns,
        layout=recipe.layout,
        row_rules=recipe.row_rules,
        reject_policy=recipe.reject_policy,
    )


def _plan_id(recipe: Recipe, profile: DatasetProfile) -> str:
    payload = {
        "recipe": {
            "version": recipe.version,
            "name": recipe.name,
            "expected_headers": recipe.expected_headers,
            "output_columns": [
                {
                    "name": column.name,
                    "source": column.source,
                    "sources": column.sources,
                    "generate": column.generate,
                    "derive": column.derive,
                    "derive_parameters": _plain(column.derive_parameters),
                    "transforms": [
                        {"name": transform.name, "parameters": _plain(transform.parameters)}
                        for transform in column.transforms
                    ],
                }
                for column in recipe.output_columns
            ],
            "layout": {
                "time_column": recipe.layout.time_column,
                "time_kind": recipe.layout.time_kind,
                "value_columns": recipe.layout.value_columns,
                "primary_value_column": recipe.layout.primary_value_column,
                "entity_column": recipe.layout.entity_column,
                "missing_tokens": recipe.layout.missing_tokens,
                "missing_default": _plain(recipe.layout.missing_default),
                "sort_by_time": recipe.layout.sort_by_time,
                "dedupe": recipe.layout.dedupe,
            },
            "row_rules": [
                {
                    "name": rule.name,
                    "column": rule.column,
                    "action": rule.action,
                    "parameters": _plain(rule.parameters),
                }
                for rule in recipe.row_rules
            ],
            "reject_policy": recipe.reject_policy,
        },
        "profile_id": profile.profile_id,
        "snapshot_sha256": profile.snapshot.content_sha256,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return f"plan-{hashlib.sha256(encoded).hexdigest()[:24]}"


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value
