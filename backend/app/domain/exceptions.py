from __future__ import annotations


class DomainError(Exception):
    """Base domain exception."""


class ValidationError(DomainError):
    """Raised when domain validation fails."""


class NotFoundError(DomainError):
    """Raised when an entity is not found."""


class ConflictError(DomainError):
    """Raised when an entity or action is in conflict with current state."""
