"""Raw-payload port required by structural Cleaner tools."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from sugarprep.domain.dataset import DatasetSnapshot


class CleanerPayloadInput(Protocol):
    def assert_unchanged(self, snapshot: DatasetSnapshot) -> None: ...

    def read_text(self, snapshot: DatasetSnapshot) -> str: ...


class CleanerToolCallInput(Protocol):
    call_id: str | None
    tool_name: str
    arguments: dict[str, Any]
    preconditions: tuple[str, ...]


class CleanerPlanInput(Protocol):
    plan_id: str
    stop_reason: str
    tool_calls: tuple[CleanerToolCallInput, ...]
    unknowns: tuple[str, ...]
    warnings: tuple[str, ...]
    diagnostics: dict[str, Any]
    metadata: dict[str, Any]


@runtime_checkable
class CleanerPlanCandidateInput(Protocol):
    """Consumer-owned view of a strict model candidate."""

    candidate_id: str
    provider_id: str
    source_sha256: str
    plan: CleanerPlanInput
