"""Deterministic, copy-producing transformation capability."""

from sugarprep.transforms.candidate_output import TransformCandidateOutput, TransformCandidateWriteSession
from sugarprep.transforms.cleaner import (
    CleanerExecutionError,
    CleanerExecutionPipeline,
    CleanerPayloadInput,
    CleanerPlanCandidateInput,
)
from sugarprep.transforms.masking import MaskingError, MaskingPipeline
from sugarprep.transforms.masking_input import MaskingPayloadInput
from sugarprep.transforms.masking_output import MaskingCandidateOutput, MaskingCandidateWriteSession
from sugarprep.transforms.pii import DETERMINISTIC_PII_ALGORITHM, MaskedText, PiiSpan, detect_pii, mask_text
from sugarprep.transforms.pipeline import TransformPipeline
from sugarprep.transforms.payload_input import TransformPayloadInput

__all__ = [
    "CleanerExecutionError",
    "CleanerExecutionPipeline",
    "CleanerPayloadInput",
    "CleanerPlanCandidateInput",
    "TransformCandidateOutput",
    "TransformCandidateWriteSession",
    "TransformPayloadInput",
    "TransformPipeline",
    "DETERMINISTIC_PII_ALGORITHM",
    "MaskedText",
    "MaskingCandidateOutput",
    "MaskingCandidateWriteSession",
    "MaskingError",
    "MaskingPayloadInput",
    "MaskingPipeline",
    "PiiSpan",
    "detect_pii",
    "mask_text",
]
