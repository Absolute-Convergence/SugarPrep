"""Internal mutable table and path-free step result values."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from io import StringIO
from typing import Any


class CleanerToolError(ValueError):
    pass


@dataclass(slots=True)
class CleanerRow:
    source_row_number: int
    values: list[str]


@dataclass(frozen=True, slots=True)
class CleanerQuarantine:
    source_row_number: int
    reason: str


@dataclass(slots=True)
class CleanerTable:
    records: list[CleanerRow]
    delimiter: str
    newline_style: str
    header_index: int = 0
    quarantine: list[CleanerQuarantine] = field(default_factory=list)

    @property
    def header_record(self) -> CleanerRow:
        if not self.records or self.header_index >= len(self.records):
            raise CleanerToolError("Cleaner table has no header row")
        return self.records[self.header_index]

    @property
    def headers(self) -> list[str]:
        return self.header_record.values

    @property
    def data_rows(self) -> list[CleanerRow]:
        return self.records[self.header_index + 1 :]

    def materialize(self, headers: list[str], rows: list[CleanerRow]) -> None:
        header_source = self.header_record.source_row_number
        self.records = [CleanerRow(header_source, list(headers)), *rows]
        self.header_index = 0


@dataclass(frozen=True, slots=True)
class CleanerStepOutcome:
    rows_input: int
    rows_output: int
    rows_quarantined: int = 0
    details: dict[str, object] = field(default_factory=dict)


def parse_cleaner_table(text: str) -> CleanerTable:
    if not isinstance(text, str) or not text.strip():
        raise CleanerToolError("Cleaner source must contain non-empty tabular text")
    delimiter = detect_delimiter(text)
    try:
        reader = csv.reader(StringIO(text, newline=""), delimiter=delimiter, strict=True)
        records = [CleanerRow(index, list(row)) for index, row in enumerate(reader, start=1)]
    except (csv.Error, UnicodeError) as exc:
        raise CleanerToolError(f"Cleaner source is not safely parseable: {exc}") from exc
    if not records:
        raise CleanerToolError("Cleaner source has no records")
    return CleanerTable(
        records=records,
        delimiter=delimiter,
        newline_style=detect_newline_style(text),
    )


def detect_delimiter(text: str) -> str:
    sample = text[: 64 * 1024]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t|;")
        if dialect.delimiter in {",", "\t", "|", ";"}:
            return dialect.delimiter
    except csv.Error:
        pass
    first_line = next((line for line in sample.splitlines() if line.strip()), "")
    counts = {delimiter: first_line.count(delimiter) for delimiter in (",", "\t", "|", ";")}
    winner = max(counts, key=counts.get)
    return winner if counts[winner] else ","


def detect_newline_style(text: str) -> str:
    styles = []
    if "\r\n" in text:
        styles.append("CRLF")
    without_crlf = text.replace("\r\n", "")
    if "\n" in without_crlf:
        styles.append("LF")
    if "\r" in without_crlf:
        styles.append("CR")
    if not styles:
        return "none"
    return styles[0] if len(styles) == 1 else "mixed"


def require_string(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CleanerToolError(f"Cleaner tool argument {key} must be a non-empty string")
    return value.strip()


def optional_columns(arguments: dict[str, Any], headers: list[str]) -> tuple[str, ...]:
    raw = arguments.get("columns")
    if raw is None and isinstance(arguments.get("column"), str):
        raw = [arguments["column"]]
    if raw is None:
        return tuple(headers)
    if not isinstance(raw, list) or not raw or not all(isinstance(item, str) and item for item in raw):
        raise CleanerToolError("Cleaner tool argument columns must be a non-empty string list")
    missing = [column for column in raw if column not in headers]
    if missing:
        raise CleanerToolError("Cleaner columns not found: " + ", ".join(missing))
    return tuple(raw)


def resolved_params(arguments: dict[str, Any]) -> dict[str, Any]:
    nested = arguments.get("params", {})
    if not isinstance(nested, dict):
        raise CleanerToolError("Cleaner tool argument params must be an object")
    ignored = {
        "columns",
        "column",
        "params",
        "output_file",
        "quarantine_file",
        "profile_json",
        "manifest_json",
    }
    return {**{key: value for key, value in arguments.items() if key not in ignored}, **nested}
