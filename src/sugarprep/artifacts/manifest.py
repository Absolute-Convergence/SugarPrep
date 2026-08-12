"""Artifact manifest and explicit artifact-state transitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import PurePath
import re

from sugarprep.domain.dataset import DatasetSnapshot
from sugarprep.domain.errors import DomainValidationError


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ArtifactState(str, Enum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"


@dataclass(frozen=True, slots=True)
class ArtifactEntry:
    name: str
    filename: str
    media_type: str
    content_sha256: str | None
    snapshot: DatasetSnapshot | None = None
    state: ArtifactState = ArtifactState.CANDIDATE

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise DomainValidationError("artifact entry name must be non-empty")
        object.__setattr__(self, "name", self.name.strip())
        for field_name in ("filename", "media_type"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"artifact entry {field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())
        if PurePath(self.filename).name != self.filename or self.filename in {".", ".."}:
            raise DomainValidationError("artifact entry filename must be a plain filename")
        if self.content_sha256 is not None:
            digest = self.content_sha256.strip().lower()
            if not _SHA256.fullmatch(digest):
                raise DomainValidationError("artifact entry content_sha256 must be a SHA-256 digest")
            object.__setattr__(self, "content_sha256", digest)
        if self.snapshot is not None and not isinstance(self.snapshot, DatasetSnapshot):
            raise DomainValidationError("artifact entry snapshot must be DatasetSnapshot when present")
        if self.snapshot is not None:
            if self.snapshot.content_sha256 != self.content_sha256:
                raise DomainValidationError("artifact entry snapshot digest must match content_sha256")
            if self.snapshot.media_type != self.media_type:
                raise DomainValidationError("artifact entry snapshot media type must match media_type")
        if not isinstance(self.state, ArtifactState):
            raise DomainValidationError("artifact entry state must be ArtifactState")


@dataclass(frozen=True, slots=True)
class ArtifactManifest:
    schema_version: int
    plan_id: str
    recipe_name: str
    profile_id: str
    result_validation_report_id: str
    entries: tuple[ArtifactEntry, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise DomainValidationError("only artifact manifest schema version 1 is supported")
        for field_name in ("plan_id", "recipe_name", "profile_id", "result_validation_report_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"artifact manifest {field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())
        entries = tuple(self.entries)
        if not entries or not all(isinstance(entry, ArtifactEntry) for entry in entries):
            raise DomainValidationError("artifact manifest requires ArtifactEntry values")
        if len({entry.name for entry in entries}) != len(entries):
            raise DomainValidationError("artifact manifest entry names must be unique")
        if len({entry.filename for entry in entries}) != len(entries):
            raise DomainValidationError("artifact manifest filenames must be unique")
        object.__setattr__(self, "entries", entries)

    def with_state(self, state: ArtifactState) -> ArtifactManifest:
        return replace(self, entries=tuple(replace(entry, state=state) for entry in self.entries))
