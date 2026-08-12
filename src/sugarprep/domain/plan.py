"""Explicit executable preparation-plan contract."""

from __future__ import annotations

from dataclasses import dataclass

from sugarprep.domain.dataset import DatasetSnapshot
from sugarprep.domain.errors import DomainValidationError
from sugarprep.domain.recipe import Layout, OutputColumn, RowRule


@dataclass(frozen=True, slots=True)
class PreparationPlan:
    """Validated, explicit instructions ready for deterministic execution."""

    plan_id: str
    version: int
    recipe_name: str
    input_snapshot: DatasetSnapshot
    output_columns: tuple[OutputColumn, ...]
    layout: Layout
    row_rules: tuple[RowRule, ...]
    reject_policy: str

    def __post_init__(self) -> None:
        for field_name in ("plan_id", "recipe_name", "reject_policy"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"{field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise DomainValidationError("plan version must be a positive integer")
        if not isinstance(self.input_snapshot, DatasetSnapshot):
            raise DomainValidationError("input_snapshot must be a DatasetSnapshot")
        output_columns = tuple(self.output_columns)
        if not output_columns:
            raise DomainValidationError("output_columns must not be empty")
        if len({column.name for column in output_columns}) != len(output_columns):
            raise DomainValidationError("plan output column names must be unique")
        object.__setattr__(self, "output_columns", output_columns)
        object.__setattr__(self, "row_rules", tuple(self.row_rules))
