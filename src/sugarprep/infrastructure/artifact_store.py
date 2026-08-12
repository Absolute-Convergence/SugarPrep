"""Atomic local-filesystem implementation of the artifact-store port."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import uuid

from sugarprep.artifacts.documents import ArtifactDocument
from sugarprep.artifacts.manifest import ArtifactEntry, ArtifactManifest, ArtifactState
from sugarprep.artifacts.store_port import ArtifactStoreReceipt
from sugarprep.domain.dataset import DatasetRef, DatasetSnapshot
from sugarprep.domain.errors import SugarPrepError
from sugarprep.infrastructure.filesystem import resolve_local_file, sha256_file


class LocalArtifactStoreError(SugarPrepError):
    pass


class LocalArtifactStore:
    """Commit already-serialized accepted contents by atomic directory rename."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def commit(
        self,
        *,
        bundle_id: str,
        accepted_manifest: ArtifactManifest,
        documents: tuple[ArtifactDocument, ...],
    ) -> ArtifactStoreReceipt:
        self._root.mkdir(parents=True, exist_ok=True)
        final_root = self._root / bundle_id
        if final_root.exists():
            raise LocalArtifactStoreError(f"artifact bundle already exists: {bundle_id}")
        stage_root = self._root / f".{bundle_id}-{uuid.uuid4().hex}.tmp"
        stage_root.mkdir(exist_ok=False)
        try:
            stored_entries = self._store_entries(
                accepted_manifest,
                documents=documents,
                stage_root=stage_root,
                final_root=final_root,
                bundle_id=bundle_id,
            )
            stored_manifest = replace(accepted_manifest, entries=stored_entries)
            stage_root.rename(final_root)
        except Exception:
            if stage_root.exists():
                shutil.rmtree(stage_root)
            raise
        return ArtifactStoreReceipt(bundle_locator=final_root.as_uri(), manifest=stored_manifest)

    def _store_entries(
        self,
        manifest: ArtifactManifest,
        *,
        documents: tuple[ArtifactDocument, ...],
        stage_root: Path,
        final_root: Path,
        bundle_id: str,
    ) -> tuple[ArtifactEntry, ...]:
        document_by_name = {document.name: document for document in documents}
        if len(document_by_name) != len(documents):
            raise LocalArtifactStoreError("serialized artifact document names must be unique")
        expected_documents = {entry.name for entry in manifest.entries if entry.snapshot is None}
        if set(document_by_name) != expected_documents:
            raise LocalArtifactStoreError("serialized documents do not match the accepted manifest")

        stored_entries: list[ArtifactEntry] = []
        for entry in manifest.entries:
            if entry.state is not ArtifactState.ACCEPTED:
                raise LocalArtifactStoreError("local artifact store accepts only accepted entries")
            if entry.snapshot is not None:
                stored_entries.append(
                    self._copy_dataset_entry(
                        entry,
                        stage_root=stage_root,
                        final_root=final_root,
                        bundle_id=bundle_id,
                    )
                )
                continue
            document = document_by_name[entry.name]
            if document.filename != entry.filename or document.media_type != entry.media_type:
                raise LocalArtifactStoreError(f"serialized artifact metadata mismatch: {entry.name}")
            if entry.content_sha256 is not None and document.content_sha256 != entry.content_sha256:
                raise LocalArtifactStoreError(f"serialized artifact fingerprint mismatch: {entry.name}")
            (stage_root / entry.filename).write_bytes(document.content)
            if sha256_file(stage_root / entry.filename) != document.content_sha256:
                raise LocalArtifactStoreError(f"serialized artifact write mismatch: {entry.name}")
            stored_entries.append(entry)
        return tuple(stored_entries)

    @staticmethod
    def _copy_dataset_entry(
        entry: ArtifactEntry,
        *,
        stage_root: Path,
        final_root: Path,
        bundle_id: str,
    ) -> ArtifactEntry:
        snapshot = entry.snapshot
        if snapshot is None:
            raise LocalArtifactStoreError("dataset artifact requires a snapshot")
        source = resolve_local_file(snapshot.reference)
        if sha256_file(source) != snapshot.content_sha256:
            raise LocalArtifactStoreError(f"artifact source changed before commit: {entry.name}")
        staged_path = stage_root / entry.filename
        shutil.copyfile(source, staged_path)
        if sha256_file(staged_path) != snapshot.content_sha256:
            raise LocalArtifactStoreError(f"artifact copy fingerprint mismatch: {entry.name}")
        stored_snapshot = DatasetSnapshot(
            reference=DatasetRef(
                dataset_id=f"{bundle_id}:{entry.name}",
                storage_locator=(final_root / entry.filename).as_uri(),
            ),
            content_sha256=snapshot.content_sha256,
            media_type=snapshot.media_type,
            headers=snapshot.headers,
            row_count=snapshot.row_count,
            provenance=snapshot.provenance,
        )
        return replace(entry, snapshot=stored_snapshot)
