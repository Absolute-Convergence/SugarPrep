"""CSV implementations of consumer-owned payload ports."""

from __future__ import annotations

from collections.abc import Iterable
import csv as csv_stdlib
from pathlib import Path
from typing import TextIO
import uuid

from sugarprep.domain.dataset import DatasetProvenance, DatasetRef, DatasetSnapshot, MaskingEvidence
from sugarprep.domain.errors import SugarPrepError
from sugarprep.infrastructure.filesystem import LocalFileResolutionError, resolve_local_file, sha256_file


class CsvPayloadError(SugarPrepError):
    """Raised when a CSV payload cannot satisfy a narrow capability port."""


class _LocalCsvPayload:
    """Shared local CSV mechanics proven common to multiple concrete ports."""

    media_type = "text/csv"

    def inspect(self, reference: DatasetRef) -> DatasetSnapshot:
        path = self._resolve_path(reference)
        content_sha256 = _sha256_file(path)
        encoding = _detect_text_encoding(path)
        dialect = _sniff_dialect(path, encoding)

        try:
            with path.open("r", encoding=encoding, newline="") as file:
                reader = csv_stdlib.reader(file, dialect=dialect)
                try:
                    headers = tuple(next(reader))
                except StopIteration as exc:
                    raise CsvPayloadError("CSV payload must contain a header row") from exc
                row_count = sum(1 for _ in reader)
        except (OSError, UnicodeError, csv_stdlib.Error) as exc:
            raise CsvPayloadError(f"unable to inspect CSV payload: {exc}") from exc

        return DatasetSnapshot(
            reference=reference,
            content_sha256=content_sha256,
            media_type=self.media_type,
            headers=headers,
            row_count=row_count,
            provenance=DatasetProvenance(operation="source"),
        )

    def iter_rows(self, snapshot: DatasetSnapshot) -> Iterable[tuple[str, ...]]:
        if snapshot.media_type != self.media_type:
            raise CsvPayloadError(f"CSV input cannot read media type {snapshot.media_type!r}")
        self.assert_unchanged(snapshot)
        path = self._resolve_path(snapshot.reference)
        encoding = _detect_text_encoding(path)
        dialect = _sniff_dialect(path, encoding)

        try:
            with path.open("r", encoding=encoding, newline="") as file:
                reader = csv_stdlib.reader(file, dialect=dialect)
                try:
                    headers = tuple(next(reader))
                except StopIteration as exc:
                    raise CsvPayloadError("CSV payload must contain a header row") from exc
                if headers != snapshot.headers:
                    raise CsvPayloadError("CSV headers no longer match the inspected snapshot")
                for row_number, row in enumerate(reader, start=2):
                    values = tuple(row)
                    if not values or all(not value.strip() for value in values):
                        yield tuple("" for _ in snapshot.headers)
                        continue
                    if len(values) != len(snapshot.headers):
                        raise CsvPayloadError(
                            f"CSV row {row_number} has {len(values)} fields; expected {len(snapshot.headers)}"
                        )
                    yield values
        except CsvPayloadError:
            raise
        except (OSError, UnicodeError, csv_stdlib.Error) as exc:
            raise CsvPayloadError(f"unable to read CSV payload: {exc}") from exc

    def assert_unchanged(self, snapshot: DatasetSnapshot) -> None:
        path = self._resolve_path(snapshot.reference)
        actual_sha256 = _sha256_file(path)
        if actual_sha256 != snapshot.content_sha256:
            raise CsvPayloadError("dataset payload changed after its snapshot was inspected")

    @staticmethod
    def _resolve_path(reference: DatasetRef) -> Path:
        try:
            return resolve_local_file(reference)
        except LocalFileResolutionError as exc:
            raise CsvPayloadError(str(exc)) from exc


class CsvProfilingPayloadInput(_LocalCsvPayload):
    """Implement profiling's payload-input port for local CSV files."""


class CsvTransformPayloadInput(_LocalCsvPayload):
    """Implement transforms' payload-input port for local CSV files."""


class CsvValidationPayloadInput(_LocalCsvPayload):
    """Implement validation's payload-input port for local CSV files."""


class CsvMaskingPayloadInput(_LocalCsvPayload):
    """Implement deterministic masking's payload-input port for local CSV files."""


class CsvCleanerPayloadInput(_LocalCsvPayload):
    """Expose source-bound raw text for structural Cleaner tools."""

    def inspect(self, reference: DatasetRef) -> DatasetSnapshot:
        """Bind raw CSV-like bytes without assuming the first record is a valid header."""

        path = self._resolve_path(reference)
        return DatasetSnapshot(
            reference=reference,
            content_sha256=_sha256_file(path),
            media_type=self.media_type,
            provenance=DatasetProvenance(operation="source"),
        )

    def read_text(self, snapshot: DatasetSnapshot) -> str:
        if snapshot.media_type != self.media_type:
            raise CsvPayloadError(f"Cleaner input cannot read media type {snapshot.media_type!r}")
        self.assert_unchanged(snapshot)
        path = self._resolve_path(snapshot.reference)
        encoding = _detect_text_encoding(path)
        try:
            return path.read_text(encoding=encoding)
        except (OSError, UnicodeError) as exc:
            raise CsvPayloadError(f"unable to read Cleaner CSV payload: {exc}") from exc


class CsvTransformCandidateOutput:
    """Atomically create immutable candidate CSV copies under an owned root."""

    def __init__(self, candidate_root: Path) -> None:
        self._candidate_root = candidate_root.resolve()

    def open_candidate(
        self,
        *,
        input_snapshot: DatasetSnapshot,
        plan_id: str,
        headers: tuple[str, ...],
    ) -> _CsvCandidateWriteSession:
        return _CsvCandidateWriteSession(
            candidate_root=self._candidate_root,
            input_snapshot=input_snapshot,
            candidate_id=plan_id,
            provenance_operation=f"prepare:{plan_id}",
            headers=headers,
        )


class CsvCleanerCandidateOutput:
    """Atomically create source-bound Cleaner candidate CSV copies."""

    def __init__(self, candidate_root: Path) -> None:
        self._candidate_root = candidate_root.resolve()

    def open_candidate(
        self,
        *,
        input_snapshot: DatasetSnapshot,
        plan_id: str,
        headers: tuple[str, ...],
    ) -> _CsvCandidateWriteSession:
        return _CsvCandidateWriteSession(
            candidate_root=self._candidate_root,
            input_snapshot=input_snapshot,
            candidate_id=plan_id,
            provenance_operation=f"cleaner:{plan_id}",
            headers=headers,
        )


class CsvMaskingCandidateOutput:
    """Atomically create masked candidate CSV copies under an owned root."""

    def __init__(self, candidate_root: Path) -> None:
        self._candidate_root = candidate_root.resolve()

    def open_candidate(
        self,
        *,
        input_snapshot: DatasetSnapshot,
        masking_id: str,
        headers: tuple[str, ...],
    ) -> _CsvCandidateWriteSession:
        return _CsvCandidateWriteSession(
            candidate_root=self._candidate_root,
            input_snapshot=input_snapshot,
            candidate_id=masking_id,
            provenance_operation=f"mask_pii:{masking_id}",
            headers=headers,
        )


class _CsvCandidateWriteSession:
    media_type = "text/csv"

    def __init__(
        self,
        *,
        candidate_root: Path,
        input_snapshot: DatasetSnapshot,
        candidate_id: str,
        provenance_operation: str,
        headers: tuple[str, ...],
    ) -> None:
        candidate_root.mkdir(parents=True, exist_ok=True)
        self._candidate_root = candidate_root
        self._input_snapshot = input_snapshot
        self._candidate_id = candidate_id
        self._provenance_operation = provenance_operation
        self._headers = headers
        self._token = uuid.uuid4().hex
        self._temp_path = candidate_root / f".{self._token}.csv.tmp"
        self._row_count = 0
        self._finished = False
        try:
            self._file: TextIO = self._temp_path.open("x", encoding="utf-8", newline="")
            self._writer = csv_stdlib.writer(self._file, lineterminator="\n")
            self._writer.writerow(headers)
        except (OSError, UnicodeError, csv_stdlib.Error) as exc:
            self._temp_path.unlink(missing_ok=True)
            raise CsvPayloadError(f"unable to open candidate CSV payload: {exc}") from exc

    def write_row(self, row: tuple[str, ...]) -> None:
        if self._finished:
            raise CsvPayloadError("candidate write session is already closed")
        values = tuple(row)
        next_row = self._row_count + 1
        if len(values) != len(self._headers):
            raise CsvPayloadError(
                f"candidate row {next_row} has {len(values)} fields; expected {len(self._headers)}"
            )
        try:
            self._writer.writerow(values)
        except (OSError, UnicodeError, csv_stdlib.Error) as exc:
            raise CsvPayloadError(f"unable to write candidate CSV row: {exc}") from exc
        self._row_count = next_row

    def commit(self, *, masking_evidence: MaskingEvidence | None = None) -> DatasetSnapshot:
        if self._finished:
            raise CsvPayloadError("candidate write session is already closed")
        try:
            self._file.close()
            content_sha256 = _sha256_file(self._temp_path)
            filename = (
                f"{_safe_filename_part(self._input_snapshot.reference.dataset_id)}-"
                f"{_safe_filename_part(self._candidate_id)}-{content_sha256[:16]}-{self._token[:8]}.csv"
            )
            candidate_path = self._candidate_root / filename
            self._temp_path.replace(candidate_path)
        except (OSError, UnicodeError, csv_stdlib.Error) as exc:
            self.abort()
            raise CsvPayloadError(f"unable to write candidate CSV payload: {exc}") from exc
        except Exception:
            self.abort()
            raise
        self._finished = True

        return DatasetSnapshot(
            reference=DatasetRef(
                dataset_id=(
                    f"{self._input_snapshot.reference.dataset_id}:candidate:"
                    f"{self._candidate_id}:{content_sha256[:12]}"
                ),
                storage_locator=candidate_path.as_uri(),
            ),
            content_sha256=content_sha256,
            media_type=self.media_type,
            headers=self._headers,
            row_count=self._row_count,
            provenance=DatasetProvenance(
                operation=self._provenance_operation,
                parent_sha256=(self._input_snapshot.content_sha256,),
                masking_evidence=masking_evidence,
            ),
        )

    def abort(self) -> None:
        if not self._finished:
            self._file.close()
            self._temp_path.unlink(missing_ok=True)
            self._finished = True


def _sha256_file(path: Path) -> str:
    try:
        return sha256_file(path)
    except LocalFileResolutionError as exc:
        raise CsvPayloadError(str(exc)) from exc


def _safe_filename_part(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in "-_" else "-" for character in value)
    return safe.strip("-")[:80] or "dataset"


def _detect_text_encoding(path: Path) -> str:
    try:
        with path.open("rb") as file:
            prefix = file.read(4)
    except OSError as exc:
        raise CsvPayloadError(f"unable to inspect CSV encoding: {exc}") from exc
    if prefix.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    return "utf-8-sig"


def _sniff_dialect(path: Path, encoding: str) -> csv_stdlib.Dialect:
    try:
        with path.open("r", encoding=encoding, newline="") as file:
            sample = file.read(64 * 1024)
        dialect = csv_stdlib.Sniffer().sniff(sample)
    except csv_stdlib.Error:
        return csv_stdlib.get_dialect("excel")
    except (OSError, UnicodeError) as exc:
        raise CsvPayloadError(f"unable to inspect CSV dialect: {exc}") from exc
    if dialect.delimiter not in {",", "\t", "|", ";"}:
        return csv_stdlib.get_dialect("excel")
    return dialect
