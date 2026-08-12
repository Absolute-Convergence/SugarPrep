from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sugarprep.inference.layout import LayoutInferenceService
from sugarprep.infrastructure.gemma_layout import GemmaLayoutProvider
from tests.unit.inference.test_layout_contract import successful_guidance, successful_profile


ASSIGNMENTS = """time_col = V1
time_kind = Index
entity_col = none
primary_value_col = V2
value_cols = V2
metadata_cols = []
forbidden_value_cols = []
"""


def make_provider(tmp_path: Path) -> GemmaLayoutProvider:
    model_path = tmp_path / "gemma-lora"
    model_path.mkdir()
    for name in ("adapter_config.json", "adapter_model.safetensors", "tokenizer.json"):
        (model_path / name).write_text("fixture", encoding="utf-8")
    command = tmp_path / "unsloth.exe"
    command.write_text("fixture", encoding="utf-8")
    return GemmaLayoutProvider(
        provider_id="gemma-layout-test",
        model_path=model_path,
        unsloth_command=command,
    )


def test_gemma_provider_uses_promoted_lora_completion_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider = make_provider(tmp_path)
    raw_output_path = tmp_path / "raw" / "layout.txt"
    observed: dict[str, object] = {}

    def fake_run(args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout="missing chat_template warning\n" + ASSIGNMENTS,
            stderr="loading promoted LoRA",
        )

    monkeypatch.setattr("sugarprep.infrastructure.gemma_layout.subprocess.run", fake_run)

    candidate = LayoutInferenceService(provider).propose(
        profile=successful_profile(),
        guidance=successful_guidance(),
        source_sha256="08cb90570617e8d4c496cf9b4ced36dd35be2596f48a91721771f55b08f2c1ad",
        raw_output_path=raw_output_path,
    )

    args = observed["args"]
    assert isinstance(args, list)
    assert args[1] == "inference"
    assert Path(args[2]).name == "gemma-lora"
    assert "--system-prompt" not in args
    assert args[-1] == "--load-in-4bit"
    assert candidate.prediction.to_dict() == {
        "time_col": "Step",
        "time_kind": "Index",
        "entity_col": None,
        "primary_value_col": "Close",
        "value_cols": ["Close"],
        "metadata_cols": [],
        "forbidden_value_cols": [],
    }
    assert candidate.recovery is not None
    assert raw_output_path.read_text(encoding="utf-8").startswith("missing chat_template")
