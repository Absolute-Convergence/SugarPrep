"""Consumer-owned port for durable artifact-bundle commits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sugarprep.artifacts.documents import ArtifactDocument
from sugarprep.artifacts.manifest import ArtifactManifest
from sugarprep.domain.errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class ArtifactStoreReceipt:
    bundle_locator: str
    manifest: ArtifactManifest

    def __post_init__(self) -> None:
        if not isinstance(self.bundle_locator, str) or not self.bundle_locator.strip():
            raise DomainValidationError("bundle_locator must be non-empty")
        object.__setattr__(self, "bundle_locator", self.bundle_locator.strip())
        if not isinstance(self.manifest, ArtifactManifest):
            raise DomainValidationError("artifact store receipt manifest must be ArtifactManifest")


class ArtifactStore(Protocol):
    def commit(
        self,
        *,
        bundle_id: str,
        accepted_manifest: ArtifactManifest,
        documents: tuple[ArtifactDocument, ...],
    ) -> ArtifactStoreReceipt: ...
