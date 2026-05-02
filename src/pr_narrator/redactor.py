"""Secret redaction with conservative defaults and an opt-in paranoid mode.

This module is the single source of truth for redaction patterns. Patterns
live as a module-level constant so they're easy to audit. Coverage is best
effort -- we catch high-blast-radius categories, not every possible secret.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Pattern:
    name: str
    regex: re.Pattern[str]
    paranoid_only: bool
    description: str


@dataclass(frozen=True)
class Redaction:
    category: str
    location: str
    span: tuple[int, int]


@dataclass(frozen=True)
class RedactionResult:
    text: str
    redactions: list[Redaction]


PATTERNS: Final[tuple[Pattern, ...]] = ()


def _shannon_entropy(s: str) -> float:
    """Bits-per-character Shannon entropy. ~4.5 separates random tokens
    from English words and most identifiers in practice."""
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def redact(
    text: str,
    location_prefix: str = "",
    paranoid: bool = False,
) -> RedactionResult:
    """Apply redaction patterns to text.

    Returns the redacted text plus a list of redactions made.
    `location_prefix` is prepended verbatim to each `Redaction.location`
    so callers can attribute redactions back to source fragments.
    """
    del location_prefix, paranoid
    return RedactionResult(text=text, redactions=[])
