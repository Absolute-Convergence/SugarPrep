"""Consumer-owned payload port for deterministic result validation."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from sugarprep.domain.dataset import DatasetRef, DatasetSnapshot


class ValidationPayloadInput(Protocol):
    def inspect(self, reference: DatasetRef) -> DatasetSnapshot: ...

    def iter_rows(self, snapshot: DatasetSnapshot) -> Iterable[tuple[str, ...]]: ...

    def assert_unchanged(self, snapshot: DatasetSnapshot) -> None: ...
