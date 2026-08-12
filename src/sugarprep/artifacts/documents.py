"""Canonical serialized artifact documents and production filenames."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import PurePath

from sugarprep.artifacts.schemas import ARTIFACT_SCHEMA_BY_NAME
from sugarprep.domain.errors import DomainValidationError


PRODUCTION_ARTIFACT_FILENAMES = {
    name: schema.filename for name, schema in ARTIFACT_SCHEMA_BY_NAME.items()
}


@dataclass(frozen=True, slots=True)
class ArtifactDocument:
    """One immutable, capability-owned serialized artifact."""

    name: str
    filename: str
    media_type: str
    content: bytes

    def __post_init__(self) -> None:
        for field_name in ("name", "filename", "media_type"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"artifact document {field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())
        if PurePath(self.filename).name != self.filename or self.filename in {".", ".."}:
            raise DomainValidationError("artifact document filename must be a plain filename")
        if not isinstance(self.content, bytes):
            raise DomainValidationError("artifact document content must be bytes")
        schema = ARTIFACT_SCHEMA_BY_NAME.get(self.name)
        if schema is None:
            raise DomainValidationError(f"unknown production artifact document: {self.name}")
        if self.filename != schema.filename or self.media_type != schema.media_type:
            raise DomainValidationError(f"artifact document {self.name} does not match its schema")

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()
