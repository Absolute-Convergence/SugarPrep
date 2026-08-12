"""Deterministic profiling evidence for dataset snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from sugarprep.domain.dataset import DatasetSnapshot
from sugarprep.domain.errors import DomainValidationError


def _non_negative(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DomainValidationError(f"{field_name} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class ColumnProfile:
    """Observed counts and examples for one ordered column."""

    name: str
    row_count: int
    missing_count: int
    numeric_success_count: int = 0
    numeric_failure_count: int = 0
    integer_like_count: int = 0
    date_like_count: int = 0
    distinct_examples: tuple[str, ...] = ()
    numeric_failure_examples: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise DomainValidationError("column profile name must be non-empty")
        object.__setattr__(self, "name", self.name.strip())
        for field_name in (
            "row_count",
            "missing_count",
            "numeric_success_count",
            "numeric_failure_count",
            "integer_like_count",
            "date_like_count",
        ):
            _non_negative(getattr(self, field_name), field_name)
        if self.missing_count > self.row_count:
            raise DomainValidationError("missing_count cannot exceed row_count")
        if self.numeric_success_count + self.numeric_failure_count > self.non_missing_count:
            raise DomainValidationError("numeric observations cannot exceed non-missing rows")
        if self.integer_like_count > self.numeric_success_count:
            raise DomainValidationError("integer_like_count cannot exceed numeric_success_count")
        if self.date_like_count > self.non_missing_count:
            raise DomainValidationError("date_like_count cannot exceed non-missing rows")
        object.__setattr__(self, "distinct_examples", tuple(str(value) for value in self.distinct_examples))
        object.__setattr__(
            self,
            "numeric_failure_examples",
            tuple(str(value) for value in self.numeric_failure_examples),
        )

    @property
    def non_missing_count(self) -> int:
        return self.row_count - self.missing_count

    @property
    def numeric_value_candidate(self) -> bool:
        return self.numeric_success_count > 0 and self.numeric_failure_count == 0

    @property
    def likely_integer(self) -> bool:
        return self.numeric_success_count > 0 and self.integer_like_count == self.numeric_success_count

    @property
    def likely_date_axis(self) -> bool:
        if self.non_missing_count == 0:
            return False
        lowered = self.name.lower()
        name_hint = any(token in lowered for token in ("date", "time", "timestamp", "month", "period"))
        return name_hint and self.date_like_count == self.non_missing_count


@dataclass(frozen=True, slots=True)
class DatasetProfile:
    """Profile evidence derived from one exact dataset snapshot."""

    profile_id: str
    snapshot: DatasetSnapshot
    columns: tuple[ColumnProfile, ...]
    profiled_row_count: int
    blank_row_count: int = 0
    mode: str = "full"
    stop_reason: str = "eof"

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise DomainValidationError("profile_id must be non-empty")
        object.__setattr__(self, "profile_id", self.profile_id.strip())
        if not isinstance(self.snapshot, DatasetSnapshot):
            raise DomainValidationError("snapshot must be a DatasetSnapshot")
        columns = tuple(self.columns)
        if not columns:
            raise DomainValidationError("columns must not be empty")
        if len({column.name for column in columns}) != len(columns):
            raise DomainValidationError("profile column names must be unique")
        if self.snapshot.headers and tuple(column.name for column in columns) != self.snapshot.headers:
            raise DomainValidationError("profile columns must match snapshot header order")
        object.__setattr__(self, "columns", columns)
        _non_negative(self.profiled_row_count, "profiled_row_count")
        _non_negative(self.blank_row_count, "blank_row_count")
        if self.snapshot.row_count is not None and self.profiled_row_count > self.snapshot.row_count:
            raise DomainValidationError("profiled_row_count cannot exceed snapshot row_count")
        for field_name in ("mode", "stop_reason"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"{field_name} must be non-empty")
