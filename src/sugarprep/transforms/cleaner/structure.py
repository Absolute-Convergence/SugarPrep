"""File-format, header, and row-shape Cleaner operations."""

from __future__ import annotations

import re
from typing import Any

from sugarprep.transforms.cleaner.model import (
    CleanerQuarantine,
    CleanerRow,
    CleanerStepOutcome,
    CleanerTable,
    CleanerToolError,
)


def detect_file_format(table: CleanerTable, _arguments: dict[str, Any]) -> CleanerStepOutcome:
    candidates = [
        table.records[index].source_row_number
        for index in _ranked_header_indexes(table.records)[:5]
    ]
    return CleanerStepOutcome(
        rows_input=len(table.data_rows),
        rows_output=len(table.data_rows),
        details={
            "delimiter": table.delimiter,
            "newline_style": table.newline_style,
            "header_candidates": candidates,
        },
    )


def select_header_row(table: CleanerTable, arguments: dict[str, Any]) -> CleanerStepOutcome:
    index = _selected_header_index(table, arguments.get("header_line_number"))
    header = [cell.strip() for cell in table.records[index].values]
    if len(header) < 2 or any(not cell for cell in header):
        raise CleanerToolError("selected Cleaner header row is not viable")
    table.records[index].values = header
    table.header_index = index
    return CleanerStepOutcome(
        rows_input=max(len(table.records) - 1, 0),
        rows_output=len(table.data_rows),
        details={"selected_header_line_number": table.header_record.source_row_number},
    )


def flatten_multirow_header(table: CleanerTable, arguments: dict[str, Any]) -> CleanerStepOutcome:
    count = arguments.get("header_row_count", 2)
    if isinstance(count, bool) or not isinstance(count, int) or count < 2:
        raise CleanerToolError("header_row_count must be an integer of at least 2")
    separator = arguments.get("separator", "_")
    if not isinstance(separator, str) or not separator:
        raise CleanerToolError("multirow header separator must be non-empty")
    selected = table.records[table.header_index : table.header_index + count]
    if len(selected) != count:
        raise CleanerToolError("source has fewer rows than header_row_count")
    width = max(len(row.values) for row in selected)
    headers: list[str] = []
    seen: dict[str, int] = {}
    for column_index in range(width):
        parts: list[str] = []
        for row in selected:
            cell = row.values[column_index].strip() if column_index < len(row.values) else ""
            if cell and cell not in parts:
                parts.append(cell)
        base = separator.join(parts) if parts else f"column_{column_index + 1}"
        occurrence = seen.get(base, 0) + 1
        seen[base] = occurrence
        headers.append(base if occurrence == 1 else f"{base}_{occurrence}")
    rows = table.records[table.header_index + count :]
    table.materialize(headers, rows)
    return CleanerStepOutcome(
        rows_input=len(rows),
        rows_output=len(rows),
        details={"header_row_count": count, "headers": list(headers)},
    )


def trim_preamble_footer(table: CleanerTable, arguments: dict[str, Any]) -> CleanerStepOutcome:
    rows_input = max(len(table.records) - 1, 0)
    selected_index = _selected_header_index(table, arguments.get("header_line_number"))
    selected = table.records[selected_index]
    headers = [cell.strip() for cell in selected.values]
    expected = len(headers)
    rows: list[CleanerRow] = []
    reasons: dict[str, int] = {}
    quarantined_before = len(table.quarantine)
    for index, row in enumerate(table.records):
        if index == selected_index:
            continue
        reason: str | None = None
        if index < selected_index:
            reason = "preamble"
        elif not row.values or all(not cell.strip() for cell in row.values):
            reason = "blank"
        elif row.values[0].strip().startswith("#"):
            reason = "comment"
        elif len(row.values) != expected:
            reason = "field_count_mismatch"
        if reason is None:
            rows.append(row)
        else:
            table.quarantine.append(CleanerQuarantine(row.source_row_number, reason))
            reasons[reason] = reasons.get(reason, 0) + 1
    table.records = [CleanerRow(selected.source_row_number, headers), *rows]
    table.header_index = 0
    return CleanerStepOutcome(
        rows_input=rows_input,
        rows_output=len(rows),
        rows_quarantined=len(table.quarantine) - quarantined_before,
        details={"quarantine_reason_counts": reasons},
    )


def repair_ragged_rows(table: CleanerTable, arguments: dict[str, Any]) -> CleanerStepOutcome:
    expected = len(table.headers)
    pad_short = bool(arguments.get("pad_short_rows", True))
    trim_extras = bool(arguments.get("trim_trailing_empty_extras", True))
    output: list[CleanerRow] = []
    repair_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for row in table.data_rows:
        values = list(row.values)
        repair_reason: str | None = None
        if not values or all(not cell.strip() for cell in values):
            reason = "blank"
        elif len(values) == expected:
            reason = None
        elif len(values) < expected and pad_short:
            values.extend([""] * (expected - len(values)))
            repair_reason = "padded_short_row"
            reason = None
        elif len(values) > expected and trim_extras and all(
            not cell.strip() for cell in values[expected:]
        ):
            values = values[:expected]
            repair_reason = "trimmed_trailing_empty_fields"
            reason = None
        else:
            reason = "unrepairable_field_count"
        if reason is not None:
            table.quarantine.append(CleanerQuarantine(row.source_row_number, reason))
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            continue
        if repair_reason is not None:
            repair_counts[repair_reason] = repair_counts.get(repair_reason, 0) + 1
        output.append(CleanerRow(row.source_row_number, values))
    rows_input = len(table.data_rows)
    table.materialize(list(table.headers), output)
    return CleanerStepOutcome(
        rows_input=rows_input,
        rows_output=len(output),
        rows_quarantined=sum(reason_counts.values()),
        details={"repair_reason_counts": repair_counts, "quarantine_reason_counts": reason_counts},
    )


def normalize_column_names(table: CleanerTable, _arguments: dict[str, Any]) -> CleanerStepOutcome:
    normalized: list[str] = []
    seen: dict[str, int] = {}
    changes = 0
    for index, source in enumerate(table.headers):
        base = source.strip() or f"column_{index + 1}"
        occurrence = seen.get(base, 0) + 1
        seen[base] = occurrence
        output = base if occurrence == 1 else f"{base}_{occurrence}"
        normalized.append(output)
        if output != source:
            changes += 1
    table.header_record.values = normalized
    return CleanerStepOutcome(
        rows_input=len(table.data_rows),
        rows_output=len(table.data_rows),
        details={"column_changes": changes, "headers": list(normalized)},
    )


def _selected_header_index(table: CleanerTable, line_number: Any) -> int:
    if line_number is None:
        ranked = _ranked_header_indexes(table.records)
        if not ranked:
            raise CleanerToolError("no viable Cleaner header candidate found")
        return ranked[0]
    if isinstance(line_number, bool) or not isinstance(line_number, int) or line_number <= 0:
        raise CleanerToolError("header_line_number must be a positive integer")
    for index, row in enumerate(table.records):
        if row.source_row_number == line_number:
            return index
    raise CleanerToolError("header_line_number is outside the source row range")


def _ranked_header_indexes(records: list[CleanerRow]) -> list[int]:
    scored: list[tuple[int, int]] = []
    for index, row in enumerate(records):
        cells = [cell.strip() for cell in row.values]
        if len(cells) < 2 or any(not cell for cell in cells):
            continue
        if not any(re.search(r"[A-Za-z_]", cell) for cell in cells):
            continue
        score = 2
        if len(set(cells)) == len(cells):
            score += 2
        following = next(
            (item for item in records[index + 1 :] if any(cell.strip() for cell in item.values)),
            None,
        )
        if following is not None and len(following.values) == len(cells):
            score += 3
        scored.append((score, index))
    return [index for _score, index in sorted(scored, key=lambda item: (-item[0], item[1]))]
