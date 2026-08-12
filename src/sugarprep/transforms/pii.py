"""Deterministic PII detection and masking primitives."""

from __future__ import annotations

from dataclasses import dataclass
import re


DETERMINISTIC_PII_ALGORITHM = "deterministic_regex_v1"
PII_PATTERNS = (
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    ("phone", re.compile(r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\w)")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    (
        "token",
        re.compile(r"\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*[^,\s}\]]+", re.IGNORECASE),
    ),
)


@dataclass(frozen=True, slots=True)
class PiiSpan:
    start: int
    end: int
    kind: str


@dataclass(frozen=True, slots=True)
class MaskedText:
    value: str
    findings: tuple[tuple[str, int], ...]


def detect_pii(text: str) -> tuple[PiiSpan, ...]:
    spans = [
        PiiSpan(match.start(), match.end(), kind)
        for kind, pattern in PII_PATTERNS
        for match in pattern.finditer(text)
    ]
    ordered = sorted(spans, key=lambda span: (span.start, -span.end, span.kind))
    merged: list[PiiSpan] = []
    for span in ordered:
        if not merged or span.start >= merged[-1].end:
            merged.append(span)
            continue
        current = merged[-1]
        if span.end > current.end:
            merged[-1] = PiiSpan(current.start, span.end, current.kind)
    return tuple(merged)


def mask_text(text: str) -> MaskedText:
    spans = detect_pii(text)
    if not spans:
        return MaskedText(text, ())
    parts: list[str] = []
    counts: dict[str, int] = {}
    cursor = 0
    for span in spans:
        parts.append(text[cursor : span.start])
        parts.append(f"[masked {span.kind}]")
        cursor = span.end
        counts[span.kind] = counts.get(span.kind, 0) + 1
    parts.append(text[cursor:])
    return MaskedText("".join(parts), tuple(sorted(counts.items())))
