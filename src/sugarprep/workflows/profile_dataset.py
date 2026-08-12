"""Profile-dataset application workflow."""

from __future__ import annotations

from sugarprep.domain import DatasetProfile, DatasetRef, DatasetSnapshot
from sugarprep.profiling import DatasetProfiler


class ProfileDatasetWorkflow:
    def __init__(self, profiler: DatasetProfiler) -> None:
        self._profiler = profiler

    def run(self, dataset: DatasetRef | DatasetSnapshot) -> DatasetProfile:
        if isinstance(dataset, DatasetSnapshot):
            return self._profiler.profile_snapshot(dataset)
        return self._profiler.profile(dataset)
