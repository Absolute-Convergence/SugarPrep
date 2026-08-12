"""Domain-level SugarPrep errors."""


class SugarPrepError(Exception):
    """Base error for supported SugarPrep operations."""


class DomainValidationError(SugarPrepError, ValueError):
    """Raised when a domain value violates a SugarPrep invariant."""
