"""Dependency-light SugarPrep domain contracts."""

from sugarprep.domain.dataset import (
    CleanerExecutionEvidence,
    CleanerToolEvidence,
    DatasetProvenance,
    DatasetRef,
    DatasetSnapshot,
    MaskingEvidence,
    MaskingFinding,
)
from sugarprep.domain.errors import DomainValidationError, SugarPrepError
from sugarprep.domain.plan import PreparationPlan
from sugarprep.domain.profile import ColumnProfile, DatasetProfile
from sugarprep.domain.recipe import Layout, OutputColumn, Recipe, RowRule, TransformSpec
from sugarprep.domain.result import (
    CleanerExecutionResult,
    DiagnosticSeverity,
    PreparationDiagnostic,
    PreparationResult,
    MaskingResult,
    RejectedRow,
)

__all__ = [
    "CleanerExecutionEvidence",
    "CleanerExecutionResult",
    "CleanerToolEvidence",
    "ColumnProfile",
    "DatasetProfile",
    "DatasetProvenance",
    "DatasetRef",
    "DatasetSnapshot",
    "DiagnosticSeverity",
    "DomainValidationError",
    "Layout",
    "MaskingEvidence",
    "MaskingFinding",
    "MaskingResult",
    "OutputColumn",
    "PreparationDiagnostic",
    "PreparationPlan",
    "PreparationResult",
    "Recipe",
    "RejectedRow",
    "RowRule",
    "SugarPrepError",
    "TransformSpec",
]
