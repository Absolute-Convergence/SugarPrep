from __future__ import annotations

import hashlib

import pytest

from sugarprep.inference import PiiInferenceContractError, PiiInferenceService, PiiSpanCandidate


class _PiiProvider:
    provider_id = "fake-pii-provider"

    def detect(self, _text: str):
        return (
            PiiSpanCandidate(0, 4, "PERSON", 0.4),
            PiiSpanCandidate(5, 12, "EMAIL", 0.9),
            PiiSpanCandidate(5, 10, "USERNAME", 0.8),
        )


def test_pii_provider_output_remains_a_filtered_candidate() -> None:
    text = "Name person@example.com"

    candidate = PiiInferenceService(_PiiProvider(), min_score=0.5).propose(text)

    assert candidate.provider_id == "fake-pii-provider"
    assert candidate.text_sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert candidate.spans == (PiiSpanCandidate(5, 12, "EMAIL", 0.9),)
    assert not hasattr(candidate, "mask")


def test_pii_provider_cannot_return_out_of_bounds_spans() -> None:
    class InvalidProvider:
        provider_id = "invalid"

        def detect(self, _text: str):
            return (PiiSpanCandidate(0, 99, "PII", 1.0),)

    with pytest.raises(PiiInferenceContractError, match="outside"):
        PiiInferenceService(InvalidProvider()).propose("short")
