"""Immutable deterministic validation reports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sugarprep.domain.errors import DomainValidationError
from sugarprep.domain.dataset import DatasetSnapshot


class ValidationSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    code: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR

    def __post_init__(self) -> None:
        for field_name in ("code", "message"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"validation finding {field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())
        if not isinstance(self.severity, ValidationSeverity):
            raise DomainValidationError("validation finding severity must be ValidationSeverity")


@dataclass(frozen=True, slots=True)
class ResultValidationReport:
    report_id: str
    plan_id: str
    input_sha256: str
    output_sha256: str | None
    findings: tuple[ValidationFinding, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("report_id", "plan_id", "input_sha256"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"result report {field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())
        if self.output_sha256 is not None and not self.output_sha256.strip():
            raise DomainValidationError("output_sha256 must be non-empty when present")
        findings = tuple(self.findings)
        if not all(isinstance(finding, ValidationFinding) for finding in findings):
            raise DomainValidationError("result report findings must be ValidationFinding values")
        object.__setattr__(self, "findings", findings)

    @property
    def passed(self) -> bool:
        return not any(finding.severity is ValidationSeverity.ERROR for finding in self.findings)


@dataclass(frozen=True, slots=True)
class DatasetValidationReport:
    report_id: str
    snapshot: DatasetSnapshot
    findings: tuple[ValidationFinding, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.report_id, str) or not self.report_id.strip():
            raise DomainValidationError("dataset report report_id must be non-empty")
        object.__setattr__(self, "report_id", self.report_id.strip())
        if not isinstance(self.snapshot, DatasetSnapshot):
            raise DomainValidationError("dataset report snapshot must be DatasetSnapshot")
        findings = tuple(self.findings)
        if not all(isinstance(finding, ValidationFinding) for finding in findings):
            raise DomainValidationError("dataset report findings must be ValidationFinding values")
        object.__setattr__(self, "findings", findings)

    @property
    def passed(self) -> bool:
        return not any(finding.severity is ValidationSeverity.ERROR for finding in self.findings)



@dataclass(frozen=True, slots=True)
class BundleValidationReport:
    report_id: str
    draft_id: str
    draft_fingerprint: str
    findings: tuple[ValidationFinding, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("report_id", "draft_id", "draft_fingerprint"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"bundle report {field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())
        findings = tuple(self.findings)
        if not all(isinstance(finding, ValidationFinding) for finding in findings):
            raise DomainValidationError("bundle report findings must be ValidationFinding values")
        object.__setattr__(self, "findings", findings)

    @property
    def passed(self) -> bool:
        return not any(finding.severity is ValidationSeverity.ERROR for finding in self.findings)


@dataclass(frozen=True, slots=True)
class SugarBotContractReport:
    report_id: str
    findings: tuple[ValidationFinding, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.report_id, str) or not self.report_id.strip():
            raise DomainValidationError("SugarBot contract report_id must be non-empty")
        object.__setattr__(self, "report_id", self.report_id.strip())
        findings = tuple(self.findings)
        if not all(isinstance(finding, ValidationFinding) for finding in findings):
            raise DomainValidationError("SugarBot contract findings must be ValidationFinding values")
        object.__setattr__(self, "findings", findings)

    @property
    def passed(self) -> bool:
        return not any(finding.severity is ValidationSeverity.ERROR for finding in self.findings)
