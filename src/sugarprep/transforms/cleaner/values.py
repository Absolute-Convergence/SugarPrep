"""Cell, derivation, reshape, deduplication, and validation Cleaner tools."""

from __future__ import annotations

import math
import re
from typing import Any

from sugarprep.transforms.cells import DEFAULT_MISSING_TOKENS, apply_transform
from sugarprep.transforms.cleaner.model import (
    CleanerQuarantine,
    CleanerRow,
    CleanerStepOutcome,
    CleanerTable,
    CleanerToolError,
    optional_columns,
    require_string,
    resolved_params,
)
from sugarprep.transforms.derivation import derive_value


DEFAULT_WIDE_MISSING_TOKENS = frozenset(
    {"", "NA", "N/A", "NULL", "NaN", "nan", "null", ".", "..", "..."}
)
MONTHLY_HEADER_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])$")
QUARTERLY_HEADER_RE = re.compile(r"^(?P<year>\d{4})-[Qq](?P<quarter>[1-4])$")
ANNUAL_HEADER_RE = re.compile(r"^(?P<year>\d{4})$")
RESERVED_WIDE_COLUMNS = frozenset(
    {
        "series_id",
        "period_start",
        "period_label",
        "period_kind",
        "period_year",
        "period_month",
        "period_quarter",
        "value",
    }
)


def normalize_missing_tokens(table: CleanerTable, arguments: dict[str, Any]) -> CleanerStepOutcome:
    columns = optional_columns(arguments, table.headers)
    indexes = {column: table.headers.index(column) for column in columns}
    tokens = arguments.get("missing_tokens", list(DEFAULT_MISSING_TOKENS))
    if not isinstance(tokens, list) or not all(isinstance(item, str) for item in tokens):
        raise CleanerToolError("missing_tokens must be a string list")
    token_set = set(tokens)
    output = str(arguments.get("missing_output", ""))
    trim = bool(arguments.get("trim", True))
    changes = {column: 0 for column in columns}
    for row in table.data_rows:
        if len(row.values) < len(table.headers):
            row.values.extend([""] * (len(table.headers) - len(row.values)))
        for column, index in indexes.items():
            original = row.values[index]
            candidate = original.strip() if trim else original
            if candidate in token_set and original != output:
                row.values[index] = output
                changes[column] += 1
    return CleanerStepOutcome(
        rows_input=len(table.data_rows),
        rows_output=len(table.data_rows),
        details={"cell_changes": changes},
    )


def parse_flexible_number(table: CleanerTable, arguments: dict[str, Any]) -> CleanerStepOutcome:
    return _transform_columns(table, arguments, "parse_flexible_number")


def parse_datetime(table: CleanerTable, arguments: dict[str, Any]) -> CleanerStepOutcome:
    return _transform_columns(table, arguments, "parse_date")


def join_datetime_parts(table: CleanerTable, arguments: dict[str, Any]) -> CleanerStepOutcome:
    output_column = require_string(arguments, "output_column")
    if output_column in table.headers:
        raise CleanerToolError(f"output column already exists: {output_column}")
    params = resolved_params(arguments)
    output: list[CleanerRow] = []
    failure_counts: dict[str, int] = {}
    rows_input = len(table.data_rows)
    for row in table.data_rows:
        if len(row.values) != len(table.headers):
            reason = "field_count_mismatch"
        else:
            source_values = dict(zip(table.headers, row.values, strict=True))
            try:
                derived = derive_value("datetime_parts", source_values, output_column, params)
            except ValueError as exc:
                reason = str(exc)
            else:
                output.append(CleanerRow(row.source_row_number, [*row.values, derived]))
                continue
        table.quarantine.append(CleanerQuarantine(row.source_row_number, reason))
        failure_counts[reason] = failure_counts.get(reason, 0) + 1
    table.materialize([*table.headers, output_column], output)
    return CleanerStepOutcome(
        rows_input=rows_input,
        rows_output=len(output),
        rows_quarantined=sum(failure_counts.values()),
        details={"output_column": output_column, "failure_reason_counts": failure_counts},
    )


def split_compound_column(table: CleanerTable, arguments: dict[str, Any]) -> CleanerStepOutcome:
    source_column = require_string(arguments, "source_column")
    delimiter = require_string(arguments, "delimiter")
    targets = arguments.get("output_columns")
    if not isinstance(targets, list) or not targets or not all(
        isinstance(item, str) and item for item in targets
    ):
        raise CleanerToolError("output_columns must be a non-empty string list")
    if source_column not in table.headers:
        raise CleanerToolError(f"source column not found: {source_column}")
    overlap = sorted(set(table.headers) & set(targets))
    if overlap:
        raise CleanerToolError("output column already exists: " + ", ".join(overlap))
    if len(targets) != len(set(targets)):
        raise CleanerToolError("output_columns must be unique")
    source_index = table.headers.index(source_column)
    trim = bool(arguments.get("trim", True))
    output: list[CleanerRow] = []
    failures = 0
    rows_input = len(table.data_rows)
    for row in table.data_rows:
        if len(row.values) != len(table.headers):
            table.quarantine.append(
                CleanerQuarantine(row.source_row_number, "field_count_mismatch")
            )
            failures += 1
            continue
        parts = row.values[source_index].split(delimiter)
        if trim:
            parts = [part.strip() for part in parts]
        if len(parts) != len(targets):
            table.quarantine.append(
                CleanerQuarantine(row.source_row_number, "split_part_count_mismatch")
            )
            failures += 1
            continue
        output.append(CleanerRow(row.source_row_number, [*row.values, *parts]))
    table.materialize([*table.headers, *targets], output)
    return CleanerStepOutcome(
        rows_input=rows_input,
        rows_output=len(output),
        rows_quarantined=failures,
        details={"source_column": source_column, "output_columns": list(targets)},
    )


def deduplicate_rows(table: CleanerTable, arguments: dict[str, Any]) -> CleanerStepOutcome:
    raw_keys = arguments.get("key_columns")
    if raw_keys is None:
        keys = tuple(table.headers)
    elif isinstance(raw_keys, list) and raw_keys and all(isinstance(item, str) for item in raw_keys):
        keys = tuple(raw_keys)
    else:
        raise CleanerToolError("key_columns must be a non-empty string list")
    missing = [column for column in keys if column not in table.headers]
    if missing:
        raise CleanerToolError("deduplicate key columns not found: " + ", ".join(missing))
    indexes = tuple(table.headers.index(column) for column in keys)
    seen: set[tuple[str, ...]] = set()
    output: list[CleanerRow] = []
    quarantined = 0
    rows_input = len(table.data_rows)
    for row in table.data_rows:
        key = (
            tuple(row.values)
            if len(row.values) != len(table.headers)
            else tuple(row.values[index] for index in indexes)
        )
        if key in seen:
            table.quarantine.append(CleanerQuarantine(row.source_row_number, "duplicate_exact"))
            quarantined += 1
            continue
        seen.add(key)
        output.append(row)
    table.materialize(list(table.headers), output)
    return CleanerStepOutcome(
        rows_input=rows_input,
        rows_output=len(output),
        rows_quarantined=quarantined,
        details={"key_columns": list(keys)},
    )


def normalize_wide_periods(table: CleanerTable, arguments: dict[str, Any]) -> CleanerStepOutcome:
    periods = [
        (index, header, parsed)
        for index, header in enumerate(table.headers)
        if (parsed := _parse_period_header(header.strip())) is not None
    ]
    if not periods:
        raise CleanerToolError("wide-period source has no YYYY, YYYY-QN, or YYYY-MM columns")
    period_indexes = {index for index, _header, _parsed in periods}
    descriptors = _descriptor_columns(table.headers, period_indexes)
    has_monthly = any(parsed["month"] is not None for _index, _header, parsed in periods)
    output_headers = [
        "series_id",
        "period_start",
        "period_label",
        "period_kind",
        "period_year",
        *(["period_month"] if has_monthly else []),
        "period_quarter",
        "value",
        *[output_name for _index, output_name in descriptors],
    ]
    configured_tokens = arguments.get("missing_tokens", [])
    if not isinstance(configured_tokens, list) or not all(
        isinstance(item, str) for item in configured_tokens
    ):
        raise CleanerToolError("wide-period missing_tokens must be a string list")
    missing_tokens = DEFAULT_WIDE_MISSING_TOKENS | set(configured_tokens)
    keep_missing = bool(arguments.get("keep_missing_values", False))
    keep_nonnumeric = bool(arguments.get("keep_nonnumeric_values", False))
    max_rows = arguments.get("max_source_rows", 0)
    if isinstance(max_rows, bool) or not isinstance(max_rows, int) or max_rows < 0:
        raise CleanerToolError("max_source_rows must be a non-negative integer")
    output: list[CleanerRow] = []
    skipped_missing = 0
    skipped_nonnumeric = 0
    source_rows = 0
    for row in table.data_rows:
        if max_rows and source_rows >= max_rows:
            break
        if not row.values or all(not value.strip() for value in row.values):
            continue
        source_rows += 1
        values = [*row.values[: len(table.headers)], *([""] * max(0, len(table.headers) - len(row.values)))]
        descriptor_values = {
            name: values[index].strip() for index, name in descriptors
        }
        series_id = _series_id(descriptor_values, source_rows)
        for index, header, parsed in periods:
            raw = values[index].strip()
            if raw in missing_tokens and not keep_missing:
                skipped_missing += 1
                continue
            if raw not in missing_tokens:
                try:
                    numeric = float(raw)
                except ValueError:
                    numeric = math.nan
                if not math.isfinite(numeric) and not keep_nonnumeric:
                    skipped_nonnumeric += 1
                    continue
            output.append(
                CleanerRow(
                    row.source_row_number,
                    [
                        series_id,
                        str(parsed["period_start"]),
                        header.strip(),
                        str(parsed["period_kind"]),
                        str(parsed["year"]),
                        *(["" if parsed["month"] is None else str(parsed["month"])] if has_monthly else []),
                        "" if parsed["quarter"] is None else str(parsed["quarter"]),
                        raw,
                        *descriptor_values.values(),
                    ],
                )
            )
    rows_input = len(table.data_rows)
    table.materialize(output_headers, output)
    skipped = skipped_missing + skipped_nonnumeric
    return CleanerStepOutcome(
        rows_input=rows_input,
        rows_output=len(output),
        rows_quarantined=0,
        details={
            "period_column_count": len(periods),
            "descriptor_column_count": len(descriptors),
            "values_skipped": skipped,
            "skipped_missing_values": skipped_missing,
            "skipped_nonnumeric_values": skipped_nonnumeric,
        },
    )


def validate_parseable_table(table: CleanerTable, _arguments: dict[str, Any]) -> CleanerStepOutcome:
    headers = table.headers
    if not headers or any(not header.strip() for header in headers):
        raise CleanerToolError("Cleaner output requires non-empty headers")
    if len(headers) != len(set(headers)):
        raise CleanerToolError("Cleaner output headers must be unique")
    for row in table.data_rows:
        if len(row.values) != len(headers):
            raise CleanerToolError(
                f"Cleaner output row {row.source_row_number} has {len(row.values)} fields; expected {len(headers)}"
            )
    return CleanerStepOutcome(
        rows_input=len(table.data_rows),
        rows_output=len(table.data_rows),
        details={"parseable": True, "headers": list(headers), "row_count": len(table.data_rows)},
    )


def _transform_columns(
    table: CleanerTable,
    arguments: dict[str, Any],
    transform_name: str,
) -> CleanerStepOutcome:
    columns = optional_columns(arguments, table.headers)
    indexes = {column: table.headers.index(column) for column in columns}
    params = resolved_params(arguments)
    output: list[CleanerRow] = []
    failures: dict[str, int] = {}
    changes = {column: 0 for column in columns}
    rows_input = len(table.data_rows)
    for row in table.data_rows:
        transformed = list(row.values)
        failure: str | None = None
        for column, index in indexes.items():
            if index >= len(transformed):
                failure = "missing_column_value"
                break
            original = transformed[index]
            try:
                parsed = apply_transform(transform_name, original, column, params)
            except ValueError as exc:
                failure = str(exc)
                break
            if parsed != original:
                changes[column] += 1
            transformed[index] = parsed
        if failure is not None:
            table.quarantine.append(CleanerQuarantine(row.source_row_number, failure))
            failures[failure] = failures.get(failure, 0) + 1
            continue
        output.append(CleanerRow(row.source_row_number, transformed))
    table.materialize(list(table.headers), output)
    return CleanerStepOutcome(
        rows_input=rows_input,
        rows_output=len(output),
        rows_quarantined=sum(failures.values()),
        details={"columns": list(columns), "cell_changes": changes, "failure_reason_counts": failures},
    )


def _parse_period_header(header: str) -> dict[str, int | str | None] | None:
    if match := MONTHLY_HEADER_RE.fullmatch(header):
        year = int(match.group("year"))
        month = int(match.group("month"))
        return {
            "period_kind": "month",
            "period_start": f"{year:04d}-{month:02d}-01",
            "year": year,
            "month": month,
            "quarter": None,
        }
    if match := QUARTERLY_HEADER_RE.fullmatch(header):
        year = int(match.group("year"))
        quarter = int(match.group("quarter"))
        return {
            "period_kind": "quarter",
            "period_start": f"{year:04d}-{((quarter - 1) * 3) + 1:02d}-01",
            "year": year,
            "month": None,
            "quarter": quarter,
        }
    if match := ANNUAL_HEADER_RE.fullmatch(header):
        year = int(match.group("year"))
        return {
            "period_kind": "year",
            "period_start": f"{year:04d}-01-01",
            "year": year,
            "month": None,
            "quarter": None,
        }
    return None


def _descriptor_columns(headers: list[str], period_indexes: set[int]) -> list[tuple[int, str]]:
    descriptors: list[tuple[int, str]] = []
    seen: dict[str, int] = {}
    for index, header in enumerate(headers):
        if index in period_indexes:
            continue
        base = re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_") or f"source_column_{index + 1}"
        if base in RESERVED_WIDE_COLUMNS:
            base = f"source_{base}"
        occurrence = seen.get(base, 0) + 1
        seen[base] = occurrence
        descriptors.append((index, base if occurrence == 1 else f"{base}_{occurrence}"))
    return descriptors


def _series_id(descriptors: dict[str, str], source_row_number: int) -> str:
    for preferred in ("series", "series_id", "title_ts", "title"):
        if value := descriptors.get(preferred, "").strip():
            return value
    parts = [f"{key}={value}" for key, value in descriptors.items() if value.strip()]
    return "|".join(parts) if parts else f"source_row_{source_row_number}"
