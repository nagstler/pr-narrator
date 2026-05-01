"""Domain-specific exceptions for pr-narrator."""

from __future__ import annotations


class SessionNotFoundError(Exception):
    """Raised when no Claude Code session matches the requested criteria."""


class AmbiguousMatchError(Exception):
    """Raised when more than one session matches a UUID prefix."""


class NotInGitRepoError(Exception):
    """Raised when git operations are attempted outside a git repository."""


class UnknownBaseRefError(Exception):
    """Raised when the requested base ref does not exist."""


class ClaudeBinaryNotFoundError(Exception):
    """Raised when the `claude` CLI cannot be found on PATH."""


class SynthesisError(Exception):
    """Raised when synthesis fails (timeout, malformed response, error from claude -p)."""
