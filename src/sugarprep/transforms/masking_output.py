"""Consumer-owned output port for copy-producing deterministic masking."""

from __future__ import annotations

from typing import Protocol

from sugarprep.domain.dataset import DatasetSnapshot, MaskingEvidence


class MaskingCandidateWriteSession(Protocol):
    def write_row(self, row: tuple[str, ...]) -> None: ...

    def commit(self, *, masking_evidence: MaskingEvidence) -> DatasetSnapshot: ...

    def abort(self) -> None: ...


class MaskingCandidateOutput(Protocol):
    def open_candidate(
        self,
        *,
        input_snapshot: DatasetSnapshot,
        masking_id: str,
        headers: tuple[str, ...],
    ) -> MaskingCandidateWriteSession: ...
