"""Consumer-owned payload port for deterministic profiling."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from sugarprep.domain.dataset import DatasetRef, DatasetSnapshot


class ProfilingPayloadInput(Protocol):
    """The exact dataset operations required by the profiling capability."""

    def inspect(self, reference: DatasetRef) -> DatasetSnapshot:
        """Resolve immutable identity and structural facts without exposing storage details."""

    def iter_rows(self, snapshot: DatasetSnapshot) -> Iterable[tuple[str, ...]]:
        """Yield ordered row values matching ``snapshot.headers``."""

    def assert_unchanged(self, snapshot: DatasetSnapshot) -> None:
        """Raise when the referenced payload no longer matches the snapshot fingerprint."""
