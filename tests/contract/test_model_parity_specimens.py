from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sugarprep.inference.cleaner import parse_cleaner_tool_plan_response
from sugarprep.inference.layout import LayoutInferenceService
from sugarprep.inference.pii import PiiInferenceService, PiiSpanCandidate


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "model_parity"


def _load(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_cleaner_specimen_freezes_all_three_stop_outcomes() -> None:
    specimen = _load("cleaner.json")
    cases = specimen["cases"]
    assert isinstance(cases, list)
    plans = [parse_cleaner_tool_plan_response(json.dumps(case["response"])) for case in cases]

    assert {plan.stop_reason for plan in plans} == {
        "execute",
        "needs_user_input",
        "cannot_repair",
    }
    execute_case = next(case for case in cases if case["response"]["stop_reason"] == "execute")
    assert execute_case["source_csv"] == execute_case["expected_output_csv"]
    assert [call.tool_name for call in plans[0].tool_calls] == [
        "detect_file_format",
        "normalize_column_names",
        "validate_parseable_table",
    ]


class _LayoutSpecimenProvider:
    provider_id = "gemma3-270m-temporal-v1"

    def __init__(self, raw_response: str) -> None:
        self._raw_response = raw_response

    def generate(self, request: dict[str, object]) -> str:
        return self._raw_response


def test_layout_specimen_freezes_lora_completion_and_recovery() -> None:
    specimen = _load("layout.json")
    service = LayoutInferenceService(_LayoutSpecimenProvider(str(specimen["raw_response"])))

    candidate = service.propose(
        profile=specimen["profile"],
        guidance=specimen["guidance"],
        source_sha256=str(specimen["source_sha256"]),
    )

    assert candidate.prediction.to_dict() == specimen["expected_prediction"]
    assert candidate.recovery is not None
    assert specimen["evidence"]["prompt_transport"] == "completion"
    assert specimen["evidence"]["gguf_required"] is False


class _PiiSpecimenProvider:
    provider_id = "sugarprep-pii-transformer-targeted-full-v0"

    def __init__(self, spans: list[dict[str, object]]) -> None:
        self._spans = spans

    def detect(self, text: str) -> tuple[PiiSpanCandidate, ...]:
        return tuple(
            PiiSpanCandidate(
                start=int(span["start"]),
                end=int(span["end"]),
                kind=str(span["kind"]),
                score=float(span["score"]),
            )
            for span in self._spans
        )


def test_pii_specimen_freezes_source_bound_spans() -> None:
    specimen = _load("pii.json")
    text = str(specimen["text"])
    candidate = PiiInferenceService(
        _PiiSpecimenProvider(specimen["spans"]),
        min_score=float(specimen["min_score"]),
    ).propose(text)

    assert candidate.text_sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert candidate.text_sha256 == specimen["text_sha256"]
    assert [text[span.start : span.end] for span in candidate.spans] == [
        item["text"] for item in specimen["spans"]
    ]
    assert [span.kind for span in candidate.spans] == [
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "city",
    ]


def test_specimens_do_not_contain_private_absolute_paths() -> None:
    serialized = "\n".join(
        (FIXTURE_ROOT / name).read_text(encoding="utf-8")
        for name in ("cleaner.json", "layout.json", "pii.json")
    )

    assert "C:\\" not in serialized
    assert "E:\\" not in serialized
    assert "Users\\" not in serialized
    assert "SugarDeploy" not in serialized


def test_specimen_manifest_binds_fixture_content() -> None:
    manifest = _load("manifest.json")
    entries = manifest["specimens"]
    assert isinstance(entries, list)

    for entry in entries:
        path = FIXTURE_ROOT / entry["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest().upper() == entry["sha256"]
