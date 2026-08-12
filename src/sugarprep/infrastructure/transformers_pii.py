"""Lazy local Transformers token-classification provider for PII candidates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sugarprep.domain.errors import SugarPrepError
from sugarprep.inference.pii import PiiSpanCandidate


class TransformersPiiProviderError(SugarPrepError):
    pass


class TransformersPiiProvider:
    def __init__(
        self,
        *,
        provider_id: str,
        model_path: Path,
        device: int | None = None,
    ) -> None:
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("provider_id must be non-empty")
        self._provider_id = provider_id.strip()
        self._model_path = model_path.resolve()
        self._device = device
        self._pipeline: Any = None

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def detect(self, text: str) -> tuple[PiiSpanCandidate, ...]:
        pipeline = self._load_pipeline()
        try:
            output = pipeline(text)
        except (RuntimeError, TypeError, ValueError) as error:
            raise TransformersPiiProviderError(f"Transformers PII inference failed: {error}") from error
        if not isinstance(output, list):
            raise TransformersPiiProviderError("Transformers PII provider returned an invalid result")
        spans: list[PiiSpanCandidate] = []
        for item in output:
            if not isinstance(item, dict):
                raise TransformersPiiProviderError("Transformers PII result item must be an object")
            try:
                spans.append(
                    PiiSpanCandidate(
                        start=int(item["start"]),
                        end=int(item["end"]),
                        kind=str(item.get("entity_group") or item.get("entity") or "pii"),
                        score=float(item.get("score") or 0.0),
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise TransformersPiiProviderError(
                    f"Transformers PII result item is invalid: {error}"
                ) from error
        return tuple(spans)

    def _load_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        if not self._model_path.is_dir():
            raise TransformersPiiProviderError("configured Transformers model directory does not exist")
        try:
            from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline
        except ImportError as error:
            raise TransformersPiiProviderError(
                "the SugarPrep pii extra is required for TransformersPiiProvider"
            ) from error
        device = self._device if self._device is not None else _automatic_device()
        try:
            tokenizer = AutoTokenizer.from_pretrained(self._model_path, local_files_only=True)
            model = AutoModelForTokenClassification.from_pretrained(
                self._model_path,
                local_files_only=True,
            )
            self._pipeline = pipeline(
                "token-classification",
                model=model,
                tokenizer=tokenizer,
                aggregation_strategy="simple",
                device=device,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise TransformersPiiProviderError(f"unable to load Transformers PII model: {error}") from error
        return self._pipeline


def _automatic_device() -> int:
    try:
        import torch
    except ImportError:
        return -1
    return 0 if torch.cuda.is_available() else -1
