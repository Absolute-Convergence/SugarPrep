"""Typed PII span candidates and token-classification provider port."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Protocol

from sugarprep.domain.errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class PiiSpanCandidate:
    start: int
    end: int
    kind: str
    score: float

    def __post_init__(self) -> None:
        for field_name in ("start", "end"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DomainValidationError(f"PII span {field_name} must be a non-negative integer")
        if self.end <= self.start:
            raise DomainValidationError("PII span end must be greater than start")
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise DomainValidationError("PII span kind must be non-empty")
        object.__setattr__(self, "kind", self.kind.strip().removeprefix("B-").removeprefix("I-"))
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise DomainValidationError("PII span score must be numeric")
        if not 0 <= float(self.score) <= 1:
            raise DomainValidationError("PII span score must be between zero and one")
        object.__setattr__(self, "score", float(self.score))


@dataclass(frozen=True, slots=True)
class PiiTextCandidate:
    candidate_id: str
    provider_id: str
    text_sha256: str
    spans: tuple[PiiSpanCandidate, ...]

    def __post_init__(self) -> None:
        for field_name in ("candidate_id", "provider_id", "text_sha256"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"PII candidate {field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())
        spans = tuple(self.spans)
        if not all(isinstance(span, PiiSpanCandidate) for span in spans):
            raise DomainValidationError("PII candidate spans must contain typed spans")
        if any(current.end > following.start for current, following in zip(spans, spans[1:])):
            raise DomainValidationError("PII candidate spans must be ordered and non-overlapping")
        object.__setattr__(self, "spans", spans)


class PiiSpanProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def detect(self, text: str) -> tuple[PiiSpanCandidate, ...]: ...


class PiiInferenceService:
    def __init__(self, provider: PiiSpanProvider, *, min_score: float = 0.5) -> None:
        if not 0 <= min_score <= 1:
            raise ValueError("PII min_score must be between zero and one")
        self._provider = provider
        self._min_score = min_score

    @property
    def provider_id(self) -> str:
        return self._provider.provider_id

    def propose(self, text: str) -> PiiTextCandidate:
        if not isinstance(text, str):
            raise TypeError("PII inference text must be a string")
        provider_spans = tuple(self._provider.detect(text))
        if not all(isinstance(span, PiiSpanCandidate) for span in provider_spans):
            raise PiiInferenceContractError("PII provider returned an untyped span")
        spans = [span for span in provider_spans if span.score >= self._min_score]
        for span in spans:
            if span.end > len(text):
                raise PiiInferenceContractError("PII provider returned a span outside the supplied text")
        merged = _merge_spans(spans)
        text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        payload = {
            "provider_id": self._provider.provider_id,
            "text_sha256": text_sha256,
            "spans": [
                {"start": span.start, "end": span.end, "kind": span.kind, "score": span.score}
                for span in merged
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return PiiTextCandidate(
            candidate_id=f"pii-candidate-{hashlib.sha256(encoded).hexdigest()[:24]}",
            provider_id=self._provider.provider_id,
            text_sha256=text_sha256,
            spans=merged,
        )


class PiiInferenceContractError(ValueError):
    pass


def _merge_spans(spans: list[PiiSpanCandidate]) -> tuple[PiiSpanCandidate, ...]:
    ordered = sorted(spans, key=lambda span: (span.start, -span.end, -span.score, span.kind))
    merged: list[PiiSpanCandidate] = []
    for span in ordered:
        if not merged or span.start >= merged[-1].end:
            merged.append(span)
            continue
        current = merged[-1]
        merged[-1] = PiiSpanCandidate(
            start=current.start,
            end=max(current.end, span.end),
            kind=current.kind if current.score >= span.score else span.kind,
            score=max(current.score, span.score),
        )
    return tuple(merged)
