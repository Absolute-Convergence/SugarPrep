"""Consumer-owned input port for deterministic transformation."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from sugarprep.domain.dataset import DatasetSnapshot


class TransformPayloadInput(Protocol):
    """Read only the exact snapshot bound into a preparation plan."""

    def iter_rows(self, snapshot: DatasetSnapshot) -> Iterable[tuple[str, ...]]: ...

    def assert_unchanged(self, snapshot: DatasetSnapshot) -> None: ...
