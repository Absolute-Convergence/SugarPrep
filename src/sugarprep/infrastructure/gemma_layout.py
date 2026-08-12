"""Local Unsloth completion provider for the promoted Gemma layout LoRA."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from sugarprep.domain.errors import SugarPrepError
from sugarprep.inference.layout import LAYOUT_RUNNER_REQUEST_VERSION, indexed_completion_prompt


class GemmaLayoutProviderError(SugarPrepError):
    pass


class GemmaLayoutProvider:
    """Invoke only the proven indexed-completion behavior of the Gemma LoRA."""

    def __init__(
        self,
        *,
        provider_id: str,
        model_path: Path,
        unsloth_command: Path,
        top_p: float = 0.8,
        top_k: int = 20,
        repetition_penalty: float = 1.0,
        max_seq_length: int = 4096,
        load_in_4bit: bool = True,
        timeout_seconds: int | None = None,
    ) -> None:
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("provider_id must be non-empty")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive when supplied")
        self._provider_id = provider_id.strip()
        self._model_path = model_path.resolve()
        self._unsloth_command = unsloth_command.resolve()
        self._top_p = top_p
        self._top_k = top_k
        self._repetition_penalty = repetition_penalty
        self._max_seq_length = max_seq_length
        self._load_in_4bit = load_in_4bit
        self._timeout_seconds = timeout_seconds

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def generate(self, request: dict[str, Any]) -> str:
        self._validate_local_assets()
        if request.get("schema_version") != LAYOUT_RUNNER_REQUEST_VERSION:
            raise GemmaLayoutProviderError(
                f"request.schema_version must be {LAYOUT_RUNNER_REQUEST_VERSION}"
            )
        if request.get("task") != "propose_typed_layout":
            raise GemmaLayoutProviderError("request.task must be propose_typed_layout")
        if request.get("prompt_style") != "indexed":
            raise GemmaLayoutProviderError("promoted Gemma requires request.prompt_style='indexed'")
        if request.get("prompt_transport") != "completion":
            raise GemmaLayoutProviderError(
                "promoted Gemma requires request.prompt_transport='completion'"
            )
        messages = request.get("messages")
        if not isinstance(messages, list):
            raise GemmaLayoutProviderError("request.messages must be a list")
        options = request.get("runner_options")
        if not isinstance(options, dict):
            options = {}
        prompt = indexed_completion_prompt(messages)
        args = [
            str(self._unsloth_command),
            "inference",
            str(self._model_path),
            prompt,
            "--max-new-tokens",
            str(_positive_int(options.get("max_new_tokens", 256), "max_new_tokens")),
            "--temperature",
            str(_non_negative_float(options.get("temperature", 0.05), "temperature")),
            "--top-p",
            str(self._top_p),
            "--top-k",
            str(self._top_k),
            "--repetition-penalty",
            str(self._repetition_penalty),
            "--max-seq-length",
            str(self._max_seq_length),
            "--load-in-4bit" if self._load_in_4bit else "--no-load-in-4bit",
        ]
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=self._timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GemmaLayoutProviderError(f"Gemma layout inference could not run: {exc}") from exc
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        _write_raw_output(request.get("raw_output_path"), output)
        if completed.returncode != 0:
            raise GemmaLayoutProviderError(
                f"Gemma layout inference exited with code {completed.returncode}: {_tail(output)}"
            )
        if not output.strip():
            raise GemmaLayoutProviderError("Gemma layout inference produced no output")
        return output

    def _validate_local_assets(self) -> None:
        if not self._model_path.is_dir():
            raise GemmaLayoutProviderError("configured Gemma LoRA directory does not exist")
        required = ("adapter_config.json", "adapter_model.safetensors", "tokenizer.json")
        missing = [name for name in required if not (self._model_path / name).is_file()]
        if missing:
            raise GemmaLayoutProviderError(
                "configured Gemma LoRA is incomplete: " + ", ".join(missing)
            )
        if not self._unsloth_command.is_file():
            raise GemmaLayoutProviderError("configured Unsloth executable does not exist")


def _write_raw_output(value: Any, output: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value:
        raise GemmaLayoutProviderError("request.raw_output_path must be a non-empty string or null")
    path = Path(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output, encoding="utf-8")


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GemmaLayoutProviderError(f"runner option {name} must be a positive integer")
    return value


def _non_negative_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise GemmaLayoutProviderError(f"runner option {name} must be a non-negative number")
    return float(value)


def _tail(text: str, *, max_chars: int = 2000) -> str:
    stripped = text.strip()
    return stripped if len(stripped) <= max_chars else stripped[-max_chars:]
