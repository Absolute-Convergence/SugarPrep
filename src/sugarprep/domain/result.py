"""Preparation execution result contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sugarprep.domain.dataset import CleanerExecutionEvidence, DatasetSnapshot, MaskingEvidence
from sugarprep.domain.errors import DomainValidationError


class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class PreparationDiagnostic:
    code: str
    message: str
    severity: DiagnosticSeverity

    def __post_init__(self) -> None:
        for field_name in ("code", "message"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"diagnostic {field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())
        if not isinstance(self.severity, DiagnosticSeverity):
            raise DomainValidationError("diagnostic severity must be DiagnosticSeverity")


@dataclass(frozen=True, slots=True)
class RejectedRow:
    source_row_number: int
    reason_code: str
    message: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.source_row_number, bool)
            or not isinstance(self.source_row_number, int)
            or self.source_row_number < 1
        ):
            raise DomainValidationError("source_row_number must be a positive integer")
        for field_name in ("reason_code", "message"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"rejected-row {field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())


@dataclass(frozen=True, slots=True)
class PreparationResult:
    """Candidate execution output; never an accepted artifact bundle."""

    plan_id: str
    input_snapshot: DatasetSnapshot
    output_snapshot: DatasetSnapshot | None
    rejected_rows: tuple[RejectedRow, ...] = ()
    warnings: tuple[str, ...] = ()
    diagnostics: tuple[PreparationDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.plan_id, str) or not self.plan_id.strip():
            raise DomainValidationError("plan_id must be non-empty")
        object.__setattr__(self, "plan_id", self.plan_id.strip())
        if not isinstance(self.input_snapshot, DatasetSnapshot):
            raise DomainValidationError("input_snapshot must be a DatasetSnapshot")
        if self.output_snapshot is not None and not isinstance(self.output_snapshot, DatasetSnapshot):
            raise DomainValidationError("output_snapshot must be DatasetSnapshot when present")
        rejected_rows = tuple(self.rejected_rows)
        diagnostics = tuple(self.diagnostics)
        if not all(isinstance(row, RejectedRow) for row in rejected_rows):
            raise DomainValidationError("rejected_rows must contain RejectedRow values")
        if not all(isinstance(item, PreparationDiagnostic) for item in diagnostics):
            raise DomainValidationError("diagnostics must contain PreparationDiagnostic values")
        warnings = tuple(str(value).strip() for value in self.warnings)
        if any(not value for value in warnings):
            raise DomainValidationError("warnings must be non-empty strings")
        object.__setattr__(self, "rejected_rows", rejected_rows)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "diagnostics", diagnostics)

    @property
    def completed(self) -> bool:
        return self.output_snapshot is not None

    @property
    def has_errors(self) -> bool:
        return any(item.severity is DiagnosticSeverity.ERROR for item in self.diagnostics)


@dataclass(frozen=True, slots=True)
class MaskingResult:
    """Original-preserving deterministic masking candidate and evidence."""

    input_snapshot: DatasetSnapshot
    output_snapshot: DatasetSnapshot
    evidence: MaskingEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.input_snapshot, DatasetSnapshot):
            raise DomainValidationError("masking input_snapshot must be DatasetSnapshot")
        if not isinstance(self.output_snapshot, DatasetSnapshot):
            raise DomainValidationError("masking output_snapshot must be DatasetSnapshot")
        if not isinstance(self.evidence, MaskingEvidence):
            raise DomainValidationError("masking evidence must be MaskingEvidence")
        if self.evidence.input_sha256 != self.input_snapshot.content_sha256:
            raise DomainValidationError("masking evidence does not match its input snapshot")
        if self.input_snapshot.row_count is not None and self.evidence.row_count != self.input_snapshot.row_count:
            raise DomainValidationError("masking evidence row count does not match its input snapshot")
        if self.output_snapshot.headers != self.input_snapshot.headers:
            raise DomainValidationError("masking must preserve ordered dataset headers")
        if (
            self.input_snapshot.row_count is not None
            and self.output_snapshot.row_count != self.input_snapshot.row_count
        ):
            raise DomainValidationError("masking must preserve dataset row count")
        if self.evidence.cell_count != self.evidence.row_count * len(self.input_snapshot.headers):
            raise DomainValidationError("masking evidence cell count does not match its dataset shape")
        if self.output_snapshot.provenance.masking_evidence != self.evidence:
            raise DomainValidationError("masked snapshot provenance must contain the exact evidence")


@dataclass(frozen=True, slots=True)
class CleanerExecutionResult:
    """A source-bound Cleaner outcome; only execute outcomes produce copies."""

    plan_candidate_id: str
    provider_id: str
    plan_id: str
    stop_reason: str
    input_snapshot: DatasetSnapshot
    output_snapshot: DatasetSnapshot | None = None
    evidence: CleanerExecutionEvidence | None = None
    unknowns: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    diagnostics: dict[str, object] | None = None
    metadata: dict[str, object] | None = None

    def __post_init__(self) -> None:
        for field_name in ("plan_candidate_id", "provider_id", "plan_id", "stop_reason"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"cleaner result {field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())
        if self.stop_reason not in {"execute", "needs_user_input", "cannot_repair"}:
            raise DomainValidationError("cleaner result stop_reason is unsupported")
        if not isinstance(self.input_snapshot, DatasetSnapshot):
            raise DomainValidationError("cleaner input_snapshot must be DatasetSnapshot")
        object.__setattr__(self, "unknowns", tuple(self.unknowns))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "diagnostics", dict(self.diagnostics or {}))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        if self.stop_reason != "execute":
            if self.output_snapshot is not None or self.evidence is not None:
                raise DomainValidationError("Cleaner stop outcomes cannot contain executed output")
            return
        if not isinstance(self.output_snapshot, DatasetSnapshot):
            raise DomainValidationError("Cleaner execute outcome requires an output snapshot")
        if not isinstance(self.evidence, CleanerExecutionEvidence):
            raise DomainValidationError("Cleaner execute outcome requires execution evidence")
        if self.evidence.plan_candidate_id != self.plan_candidate_id:
            raise DomainValidationError("Cleaner evidence does not match its plan candidate")
        if self.evidence.provider_id != self.provider_id:
            raise DomainValidationError("Cleaner evidence does not match its provider")
        if self.evidence.plan_id != self.plan_id:
            raise DomainValidationError("Cleaner evidence does not match its plan")
        if self.evidence.input_sha256 != self.input_snapshot.content_sha256:
            raise DomainValidationError("Cleaner evidence does not match its input snapshot")
        if self.evidence.output_sha256 != self.output_snapshot.content_sha256:
            raise DomainValidationError("Cleaner evidence does not match its output snapshot")
        if self.output_snapshot.provenance.cleaner_evidence != self.evidence:
            raise DomainValidationError("Cleaner output provenance must contain the exact evidence")
        if self.input_snapshot.content_sha256 not in self.output_snapshot.provenance.parent_sha256:
            raise DomainValidationError("Cleaner output provenance must reference its input snapshot")
        if not self.evidence.validation_passed:
            raise DomainValidationError("Cleaner execute outcome requires passed deterministic validation")
