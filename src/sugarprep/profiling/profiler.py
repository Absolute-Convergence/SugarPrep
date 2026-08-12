"""Deterministic, storage-agnostic dataset profiler."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sugarprep.domain.dataset import DatasetRef, DatasetSnapshot
from sugarprep.domain.errors import DomainValidationError
from sugarprep.domain.profile import ColumnProfile, DatasetProfile
from sugarprep.profiling.payload_input import ProfilingPayloadInput


DEFAULT_MISSING_TOKENS = frozenset({"", "NA", "N/A", "NULL", "NaN", "nan", "null"})
DATE_FORMATS = (
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


@dataclass(frozen=True, slots=True)
class AdaptiveProfilePolicy:
    min_rows: int = 10_000
    batch_size: int = 5_000
    stability_batches: int = 4
    max_rows: int = 250_000

    def __post_init__(self) -> None:
        for field_name in ("min_rows", "batch_size", "stability_batches", "max_rows"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise DomainValidationError(f"adaptive {field_name} must be a positive integer")
        if self.max_rows < self.min_rows:
            raise DomainValidationError("adaptive max_rows cannot be less than min_rows")


@dataclass(slots=True)
class _ColumnAccumulator:
    name: str
    row_count: int = 0
    missing_count: int = 0
    numeric_success_count: int = 0
    numeric_failure_count: int = 0
    integer_like_count: int = 0
    date_like_count: int = 0
    distinct_examples: list[str] = field(default_factory=list)
    numeric_failure_examples: list[str] = field(default_factory=list)
    seen_examples: set[str] = field(default_factory=set)

    @property
    def non_missing_count(self) -> int:
        return self.row_count - self.missing_count

    def freeze(self) -> ColumnProfile:
        return ColumnProfile(
            name=self.name,
            row_count=self.row_count,
            missing_count=self.missing_count,
            numeric_success_count=self.numeric_success_count,
            numeric_failure_count=self.numeric_failure_count,
            integer_like_count=self.integer_like_count,
            date_like_count=self.date_like_count,
            distinct_examples=tuple(self.distinct_examples),
            numeric_failure_examples=tuple(self.numeric_failure_examples),
        )


class DatasetProfiler:
    """Profile a dataset through the capability's narrow payload port."""

    def __init__(self, payload_input: ProfilingPayloadInput, *, max_distinct_samples: int = 20) -> None:
        if max_distinct_samples <= 0:
            raise DomainValidationError("max_distinct_samples must be positive")
        self._payload_input = payload_input
        self._max_distinct_samples = max_distinct_samples

    def profile(
        self,
        reference: DatasetRef,
        *,
        adaptive: bool = False,
        adaptive_policy: AdaptiveProfilePolicy | None = None,
        profile_id: str | None = None,
    ) -> DatasetProfile:
        snapshot = self._payload_input.inspect(reference)
        return self.profile_snapshot(
            snapshot,
            adaptive=adaptive,
            adaptive_policy=adaptive_policy,
            profile_id=profile_id,
        )

    def profile_snapshot(
        self,
        snapshot: DatasetSnapshot,
        *,
        adaptive: bool = False,
        adaptive_policy: AdaptiveProfilePolicy | None = None,
        profile_id: str | None = None,
    ) -> DatasetProfile:
        """Profile an existing immutable snapshot without discarding its provenance."""

        self._payload_input.assert_unchanged(snapshot)
        if not snapshot.headers:
            raise DomainValidationError("profiling requires at least one header")

        policy = adaptive_policy or AdaptiveProfilePolicy()
        columns = [_ColumnAccumulator(name=header) for header in snapshot.headers]
        profiled_row_count = 0
        blank_row_count = 0
        stop_reason = "eof"
        stable_signature_count = 0
        previous_signature: tuple[Any, ...] | None = None

        for row in self._payload_input.iter_rows(snapshot):
            if len(row) != len(columns):
                raise DomainValidationError("profiling payload row width does not match snapshot headers")
            if all(not value.strip() for value in row):
                blank_row_count += 1
                continue

            profiled_row_count += 1
            for column, raw_value in zip(columns, row, strict=True):
                self._update_column(column, raw_value)

            if adaptive:
                if profiled_row_count >= policy.max_rows:
                    stop_reason = "adaptive_max_rows"
                    break
                if profiled_row_count >= policy.min_rows and profiled_row_count % policy.batch_size == 0:
                    signature = _profile_signature(columns)
                    if signature == previous_signature:
                        stable_signature_count += 1
                    else:
                        previous_signature = signature
                        stable_signature_count = 1
                    if stable_signature_count >= policy.stability_batches:
                        stop_reason = "adaptive_stable"
                        break

        self._payload_input.assert_unchanged(snapshot)
        mode = "adaptive" if adaptive else "full"
        resolved_profile_id = profile_id or (
            f"profile-{snapshot.content_sha256[:16]}-{mode}-{profiled_row_count}"
        )
        return DatasetProfile(
            profile_id=resolved_profile_id,
            snapshot=snapshot,
            columns=tuple(column.freeze() for column in columns),
            profiled_row_count=profiled_row_count,
            blank_row_count=blank_row_count,
            mode=mode,
            stop_reason=stop_reason,
        )

    def _update_column(self, profile: _ColumnAccumulator, raw_value: str) -> None:
        profile.row_count += 1
        value = raw_value.strip()
        if value in DEFAULT_MISSING_TOKENS:
            profile.missing_count += 1
            return

        if len(profile.seen_examples) < self._max_distinct_samples and value not in profile.seen_examples:
            profile.seen_examples.add(value)
            profile.distinct_examples.append(value)

        numeric_value = _parse_plain_numeric(value)
        if numeric_value is None:
            profile.numeric_failure_count += 1
            if value not in profile.numeric_failure_examples and len(profile.numeric_failure_examples) < 10:
                profile.numeric_failure_examples.append(value)
        else:
            profile.numeric_success_count += 1
            if numeric_value.is_integer():
                profile.integer_like_count += 1

        if _should_attempt_date_parse(profile.name, value, numeric_value is not None) and _looks_like_date(value):
            profile.date_like_count += 1


def _profile_signature(columns: list[_ColumnAccumulator]) -> tuple[Any, ...]:
    return tuple(
        (
            column.name,
            column.numeric_success_count > 0 and column.numeric_failure_count == 0,
            column.numeric_success_count > 0 and column.integer_like_count == column.numeric_success_count,
            column.date_like_count == column.non_missing_count and column.non_missing_count > 0,
            column.numeric_failure_count > 0,
            round((column.missing_count / column.row_count) * 100) if column.row_count else 0,
        )
        for column in columns
    )


def _parse_plain_numeric(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _looks_like_date(value: str) -> bool:
    if "T" in value:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            pass
    for date_format in DATE_FORMATS:
        try:
            datetime.strptime(value, date_format)
            return True
        except ValueError:
            continue
    return False


def _should_attempt_date_parse(column_name: str, value: str, is_numeric: bool) -> bool:
    if is_numeric:
        return value.isdigit() and len(value) in (6, 8)
    lowered_name = column_name.lower()
    return (
        any(token in lowered_name for token in ("date", "time", "timestamp", "month", "period"))
        or "T" in value
        or "/" in value
        or "-" in value
    )
