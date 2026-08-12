from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from sugarprep.inference.layout import LayoutInferenceService, build_indexed_layout_request


_LAYOUT_SPECIMEN = json.loads(
    (Path(__file__).parents[2] / "fixtures" / "model_parity" / "layout.json").read_text(
        encoding="utf-8"
    )
)


def successful_profile() -> dict[str, object]:
    return copy.deepcopy(_LAYOUT_SPECIMEN["profile"])


def successful_guidance() -> dict[str, object]:
    return copy.deepcopy(_LAYOUT_SPECIMEN["guidance"])


SUCCESSFUL_RAW_OUTPUT = str(_LAYOUT_SPECIMEN["raw_response"])


class SuccessfulLayoutProvider:
    provider_id = "gemma-layout-test"

    def __init__(self) -> None:
        self.request: dict[str, object] | None = None

    def generate(self, request: dict[str, object]) -> str:
        self.request = request
        return SUCCESSFUL_RAW_OUTPUT


def test_request_is_exact_indexed_completion_contract() -> None:
    request = build_indexed_layout_request(successful_profile(), successful_guidance())

    assert request["prompt_style"] == "indexed"
    assert request["prompt_transport"] == "completion"
    assert request["column_label_map"] == {"V1": "Step", "V2": "Close", "V3": "Volume"}
    messages = request["messages"]
    assert isinstance(messages, list)
    assert messages[0]["content"].startswith("You are SugarPrep's semantic layout planner")
    assert "time_col = V1" in messages[1]["content"]


def test_retained_successful_output_recovers_to_typed_layout() -> None:
    provider = SuccessfulLayoutProvider()
    service = LayoutInferenceService(provider)
    digest = hashlib.sha256(b"Step,Close,Volume\n1,101,1200\n").hexdigest()

    candidate = service.propose(
        profile=successful_profile(),
        guidance=successful_guidance(),
        source_sha256=digest,
    )

    assert candidate.prediction.to_dict() == _LAYOUT_SPECIMEN["expected_prediction"]
    assert candidate.recovery is not None
    assert candidate.recovery["strategy"] == "key_value_assignments"
    assert candidate.source_sha256 == digest
    assert provider.request is not None
