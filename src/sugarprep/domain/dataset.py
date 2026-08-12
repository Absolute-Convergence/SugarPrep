"""Dataset identity and immutable snapshot contracts.

These values intentionally expose no tabular operations. ``storage_locator`` is
an opaque token interpreted only by injected infrastructure adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from sugarprep.domain.errors import DomainValidationError


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _sha256(value: str, field_name: str) -> str:
    normalized = _required_text(value, field_name).lower()
    if not _SHA256.fullmatch(normalized):
        raise DomainValidationError(f"{field_name} must be a 64-character SHA-256 hex digest")
    return normalized


@dataclass(frozen=True, slots=True)
class DatasetRef:
    """Logical dataset identity plus an opaque infrastructure locator."""

    dataset_id: str
    storage_locator: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _required_text(self.dataset_id, "dataset_id"))
        object.__setattr__(
            self,
            "storage_locator",
            _required_text(self.storage_locator, "storage_locator"),
        )


@dataclass(frozen=True, slots=True)
class MaskingFinding:
    kind: str
    count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _required_text(self.kind, "masking finding kind"))
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count <= 0:
            raise DomainValidationError("masking finding count must be a positive integer")


@dataclass(frozen=True, slots=True)
class MaskingEvidence:
    """Masking evidence bound to one exact input snapshot."""

    evidence_id: str
    algorithm: str
    input_sha256: str
    row_count: int
    cell_count: int
    masked_cell_count: int
    findings: tuple[MaskingFinding, ...] = ()
    model_provider_id: str | None = None
    model_detection_count: int = 0
    deterministic_detection_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _required_text(self.evidence_id, "masking evidence_id"))
        object.__setattr__(self, "algorithm", _required_text(self.algorithm, "masking algorithm"))
        object.__setattr__(self, "input_sha256", _sha256(self.input_sha256, "masking input_sha256"))
        for field_name in (
            "row_count",
            "cell_count",
            "masked_cell_count",
            "model_detection_count",
            "deterministic_detection_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DomainValidationError(f"masking {field_name} must be a non-negative integer")
        if self.masked_cell_count > self.cell_count:
            raise DomainValidationError("masked_cell_count cannot exceed cell_count")
        findings = tuple(self.findings)
        if not all(isinstance(finding, MaskingFinding) for finding in findings):
            raise DomainValidationError("masking evidence findings must be MaskingFinding values")
        if len({finding.kind for finding in findings}) != len(findings):
            raise DomainValidationError("masking evidence finding kinds must be unique")
        object.__setattr__(self, "findings", findings)
        if self.model_provider_id is not None:
            object.__setattr__(
                self,
                "model_provider_id",
                _required_text(self.model_provider_id, "masking model_provider_id"),
            )
        if self.model_detection_count and self.model_provider_id is None:
            raise DomainValidationError("model detections require a model_provider_id")

    @property
    def finding_count(self) -> int:
        return sum(finding.count for finding in self.findings)


@dataclass(frozen=True, slots=True)
class CleanerToolEvidence:
    """One deterministic tool execution without filesystem details."""

    call_id: str
    tool_name: str
    arguments: dict[str, object]
    rows_input: int
    rows_output: int
    rows_quarantined: int = 0
    details: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "call_id", _required_text(self.call_id, "cleaner call_id"))
        object.__setattr__(self, "tool_name", _required_text(self.tool_name, "cleaner tool_name"))
        if not isinstance(self.arguments, dict):
            raise DomainValidationError("cleaner tool arguments must be an object")
        object.__setattr__(self, "arguments", dict(self.arguments))
        for field_name in ("rows_input", "rows_output", "rows_quarantined"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DomainValidationError(f"cleaner {field_name} must be a non-negative integer")
        if not isinstance(self.details, dict):
            raise DomainValidationError("cleaner tool details must be an object")
        object.__setattr__(self, "details", dict(self.details))


@dataclass(frozen=True, slots=True)
class CleanerExecutionEvidence:
    """Deterministic execution evidence bound to one model candidate and copy."""

    evidence_id: str
    plan_candidate_id: str
    provider_id: str
    plan_id: str
    input_sha256: str
    output_sha256: str
    tool_executions: tuple[CleanerToolEvidence, ...]
    rows_quarantined: int
    validation_passed: bool

    def __post_init__(self) -> None:
        for field_name in ("evidence_id", "plan_candidate_id", "provider_id", "plan_id"):
            object.__setattr__(self, field_name, _required_text(getattr(self, field_name), field_name))
        object.__setattr__(self, "input_sha256", _sha256(self.input_sha256, "cleaner input_sha256"))
        object.__setattr__(self, "output_sha256", _sha256(self.output_sha256, "cleaner output_sha256"))
        executions = tuple(self.tool_executions)
        if not executions or not all(isinstance(item, CleanerToolEvidence) for item in executions):
            raise DomainValidationError("cleaner evidence requires typed tool executions")
        if len({item.call_id for item in executions}) != len(executions):
            raise DomainValidationError("cleaner evidence call_ids must be unique")
        object.__setattr__(self, "tool_executions", executions)
        if (
            isinstance(self.rows_quarantined, bool)
            or not isinstance(self.rows_quarantined, int)
            or self.rows_quarantined < 0
        ):
            raise DomainValidationError("cleaner rows_quarantined must be a non-negative integer")
        if not isinstance(self.validation_passed, bool):
            raise DomainValidationError("cleaner validation_passed must be boolean")
        expected_quarantined = sum(item.rows_quarantined for item in executions)
        if self.rows_quarantined != expected_quarantined:
            raise DomainValidationError(
                "cleaner rows_quarantined must equal the deterministic tool evidence total"
            )


@dataclass(frozen=True, slots=True)
class DatasetProvenance:
    """Minimal lineage for one immutable dataset snapshot."""

    operation: str
    parent_sha256: tuple[str, ...] = ()
    masking_evidence: MaskingEvidence | None = None
    cleaner_evidence: CleanerExecutionEvidence | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation", _required_text(self.operation, "operation"))
        object.__setattr__(
            self,
            "parent_sha256",
            tuple(_sha256(value, "parent_sha256") for value in self.parent_sha256),
        )
        if self.masking_evidence is not None:
            if not isinstance(self.masking_evidence, MaskingEvidence):
                raise DomainValidationError("masking_evidence must be MaskingEvidence when present")
            if self.masking_evidence.input_sha256 not in self.parent_sha256:
                raise DomainValidationError("masking evidence input must be a provenance parent")
        if self.cleaner_evidence is not None:
            if not isinstance(self.cleaner_evidence, CleanerExecutionEvidence):
                raise DomainValidationError("cleaner_evidence must be CleanerExecutionEvidence when present")
            if self.cleaner_evidence.input_sha256 not in self.parent_sha256:
                raise DomainValidationError("cleaner evidence input must be a provenance parent")


@dataclass(frozen=True, slots=True)
class DatasetSnapshot:
    """Identity and observed structural facts for exact immutable content."""

    reference: DatasetRef
    content_sha256: str
    media_type: str
    headers: tuple[str, ...] = ()
    row_count: int | None = None
    provenance: DatasetProvenance = field(default_factory=lambda: DatasetProvenance(operation="source"))

    def __post_init__(self) -> None:
        if not isinstance(self.reference, DatasetRef):
            raise DomainValidationError("reference must be a DatasetRef")
        object.__setattr__(self, "content_sha256", _sha256(self.content_sha256, "content_sha256"))
        object.__setattr__(self, "media_type", _required_text(self.media_type, "media_type"))

        headers = tuple(_required_text(header, "header") for header in self.headers)
        if len(headers) != len(set(headers)):
            raise DomainValidationError("headers must be unique and ordered")
        object.__setattr__(self, "headers", headers)

        if self.row_count is not None and (
            isinstance(self.row_count, bool) or not isinstance(self.row_count, int) or self.row_count < 0
        ):
            raise DomainValidationError("row_count must be a non-negative integer when present")
        if not isinstance(self.provenance, DatasetProvenance):
            raise DomainValidationError("provenance must be DatasetProvenance")
