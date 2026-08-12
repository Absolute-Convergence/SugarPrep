"""Consumer-owned output port for copy-producing transformation."""

from __future__ import annotations

from typing import Protocol

from sugarprep.domain.dataset import DatasetSnapshot


class TransformCandidateWriteSession(Protocol):
    """Bounded-memory atomic write session for one candidate snapshot."""

    def write_row(self, row: tuple[str, ...]) -> None: ...

    def commit(self) -> DatasetSnapshot: ...

    def abort(self) -> None: ...


class TransformCandidateOutput(Protocol):
    """Open an atomic candidate write session."""

    def open_candidate(
        self,
        *,
        input_snapshot: DatasetSnapshot,
        plan_id: str,
        headers: tuple[str, ...],
    ) -> TransformCandidateWriteSession: ...
