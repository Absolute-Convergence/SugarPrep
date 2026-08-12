"""Deterministically mask a dataset into an original-preserving candidate."""

from __future__ import annotations

from sugarprep.domain import DatasetSnapshot, MaskingResult
from sugarprep.transforms import MaskingPipeline


class MaskDatasetWorkflow:
    def __init__(self, pipeline: MaskingPipeline) -> None:
        self._pipeline = pipeline

    def run(self, snapshot: DatasetSnapshot) -> MaskingResult:
        return self._pipeline.execute(snapshot)
