"""Domain-specific exceptions for pr-narrator."""

from __future__ import annotations


class SessionNotFoundError(Exception):
    """Raised when no Claude Code session matches the requested criteria."""


class AmbiguousMatchError(Exception):
    """Raised when more than one session matches a UUID prefix."""
