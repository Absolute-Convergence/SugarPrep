"""Storage-independent deterministic PII masking pipeline."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from sugarprep.domain.dataset import DatasetSnapshot, MaskingEvidence, MaskingFinding
from sugarprep.domain.errors import SugarPrepError
from sugarprep.domain.result import MaskingResult
from sugarprep.transforms.masking_input import MaskingPayloadInput
from sugarprep.transforms.masking_output import MaskingCandidateOutput
from sugarprep.transforms.pii import DETERMINISTIC_PII_ALGORITHM, detect_pii, mask_text


MODEL_BACKED_PII_ALGORITHM = "pii_ner_plus_deterministic_regex_v1"


class PiiDetectionSpan(Protocol):
    start: int
    end: int
    kind: str
    score: float


class PiiDetectionCandidate(Protocol):
    spans: tuple[PiiDetectionSpan, ...]


class PiiCandidateSource(Protocol):
    @property
    def provider_id(self) -> str: ...

    def propose(self, text: str) -> PiiDetectionCandidate: ...


class MaskingError(SugarPrepError):
    pass


class MaskingPipeline:
    """Produce an original-preserving masked candidate with exact evidence."""

    def __init__(
        self,
        payload_input: MaskingPayloadInput,
        candidate_output: MaskingCandidateOutput,
        pii_inference: PiiCandidateSource | None = None,
    ) -> None:
        self._payload_input = payload_input
        self._candidate_output = candidate_output
        self._pii_inference = pii_inference

    def execute(self, snapshot: DatasetSnapshot) -> MaskingResult:
        if not snapshot.headers:
            raise MaskingError("deterministic masking requires at least one header")
        self._payload_input.assert_unchanged(snapshot)
        masking_identity = snapshot.content_sha256
        if self._pii_inference is not None:
            masking_identity += ":" + self._pii_inference.provider_id
        masking_id = f"mask-{hashlib.sha256(masking_identity.encode('utf-8')).hexdigest()[:24]}"
        output_candidate = self._candidate_output.open_candidate(
            input_snapshot=snapshot,
            masking_id=masking_id,
            headers=snapshot.headers,
        )
        row_count = 0
        cell_count = 0
        masked_cell_count = 0
        counts: dict[str, int] = {}
        model_detection_count = 0
        deterministic_detection_count = 0
        try:
            for row_count, values in enumerate(self._payload_input.iter_rows(snapshot), start=1):
                if len(values) != len(snapshot.headers):
                    raise MaskingError(
                        f"source row {row_count} has {len(values)} values; expected {len(snapshot.headers)}"
                    )
                masked_values: list[str] = []
                for value in values:
                    cell_count += 1
                    if self._pii_inference is None:
                        masked = mask_text(value)
                        masked_value = masked.value
                        findings = masked.findings
                    else:
                        deterministic_spans = detect_pii(value)
                        pii_candidate = self._pii_inference.propose(value)
                        deterministic_detection_count += len(deterministic_spans)
                        model_detection_count += len(pii_candidate.spans)
                        combined = _merge_detected_spans(deterministic_spans, pii_candidate.spans)
                        masked_value = _apply_detected_spans(value, combined)
                        finding_counts: dict[str, int] = {}
                        for span in combined:
                            finding_counts[span.kind] = finding_counts.get(span.kind, 0) + 1
                        findings = tuple(sorted(finding_counts.items()))
                    if masked_value != value:
                        masked_cell_count += 1
                    for kind, count in findings:
                        counts[kind] = counts.get(kind, 0) + count
                    if detect_pii(masked_value):
                        raise MaskingError("deterministic masking left a recognized PII span")
                    masked_values.append(masked_value)
                output_candidate.write_row(tuple(masked_values))
            self._payload_input.assert_unchanged(snapshot)
            evidence = _create_evidence(
                snapshot=snapshot,
                row_count=row_count,
                cell_count=cell_count,
                masked_cell_count=masked_cell_count,
                counts=counts,
                model_provider_id=(
                    self._pii_inference.provider_id if self._pii_inference is not None else None
                ),
                model_detection_count=model_detection_count,
                deterministic_detection_count=deterministic_detection_count,
            )
            output_snapshot = output_candidate.commit(masking_evidence=evidence)
        except Exception:
            output_candidate.abort()
            raise
        return MaskingResult(
            input_snapshot=snapshot,
            output_snapshot=output_snapshot,
            evidence=evidence,
        )


def _create_evidence(
    *,
    snapshot: DatasetSnapshot,
    row_count: int,
    cell_count: int,
    masked_cell_count: int,
    counts: dict[str, int],
    model_provider_id: str | None,
    model_detection_count: int,
    deterministic_detection_count: int,
) -> MaskingEvidence:
    algorithm = MODEL_BACKED_PII_ALGORITHM if model_provider_id is not None else DETERMINISTIC_PII_ALGORITHM
    payload = {
        "algorithm": algorithm,
        "input_sha256": snapshot.content_sha256,
        "row_count": row_count,
        "cell_count": cell_count,
        "masked_cell_count": masked_cell_count,
        "findings": sorted(counts.items()),
        "model_provider_id": model_provider_id,
        "model_detection_count": model_detection_count,
        "deterministic_detection_count": deterministic_detection_count,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return MaskingEvidence(
        evidence_id=f"masking-{hashlib.sha256(encoded).hexdigest()[:24]}",
        algorithm=algorithm,
        input_sha256=snapshot.content_sha256,
        row_count=row_count,
        cell_count=cell_count,
        masked_cell_count=masked_cell_count,
        findings=tuple(MaskingFinding(kind=kind, count=count) for kind, count in sorted(counts.items())),
        model_provider_id=model_provider_id,
        model_detection_count=model_detection_count,
        deterministic_detection_count=deterministic_detection_count,
    )


@dataclass(frozen=True, slots=True)
class _DetectedSpan:
    start: int
    end: int
    kind: str
    source: str
    score: float


def _merge_detected_spans(deterministic_spans, model_spans) -> tuple[_DetectedSpan, ...]:
    spans = [
        *(
            _DetectedSpan(span.start, span.end, span.kind, "deterministic", 1.0)
            for span in deterministic_spans
        ),
        *(
            _DetectedSpan(span.start, span.end, span.kind, "model", span.score)
            for span in model_spans
        ),
    ]
    ordered = sorted(
        spans,
        key=lambda span: (
            span.start,
            -span.end,
            0 if span.source == "deterministic" else 1,
        ),
    )
    merged: list[_DetectedSpan] = []
    for span in ordered:
        if not merged or span.start > merged[-1].end:
            merged.append(span)
            continue
        current = merged[-1]
        kind = current.kind
        source = current.source
        if source != "deterministic" and span.source == "deterministic":
            kind = span.kind
            source = span.source
        merged[-1] = _DetectedSpan(
            current.start,
            max(current.end, span.end),
            kind,
            source,
            max(current.score, span.score),
        )
    return tuple(merged)


def _apply_detected_spans(text: str, spans: tuple[_DetectedSpan, ...]) -> str:
    if not spans:
        return text
    parts: list[str] = []
    cursor = 0
    for span in spans:
        if span.start < cursor:
            continue
        parts.append(text[cursor : span.start])
        parts.append(f"[masked {span.kind}]")
        cursor = span.end
    parts.append(text[cursor:])
    return "".join(parts)
