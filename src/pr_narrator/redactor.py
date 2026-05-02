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

ENTROPY_THRESHOLD: Final[float] = 4.5
PLACEHOLDER_TEMPLATE: Final[str] = "[REDACTED:{name}]"

# Patterns that span only a sub-group of the regex (the "value" portion).
# For these, we redact match.span(1), not match.span().
_VALUE_GROUP_PATTERNS: Final[frozenset[str]] = frozenset(
    {"aws_secret_key", "generic_secret_assignment"}
)


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


PATTERNS: Final[tuple[Pattern, ...]] = (
    Pattern(
        name="anthropic_api_key",
        regex=re.compile(r"sk-ant-[a-zA-Z0-9_-]{40,}"),
        paranoid_only=False,
        description="Anthropic API key",
    ),
    Pattern(
        name="openai_project_key",
        regex=re.compile(r"sk-proj-[a-zA-Z0-9_-]{40,}"),
        paranoid_only=False,
        description="OpenAI project API key",
    ),
    Pattern(
        name="openai_api_key",
        regex=re.compile(r"sk-[a-zA-Z0-9]{48}"),
        paranoid_only=False,
        description="OpenAI API key",
    ),
    Pattern(
        name="aws_access_key",
        regex=re.compile(r"AKIA[0-9A-Z]{16}"),
        paranoid_only=False,
        description="AWS access key ID",
    ),
    Pattern(
        name="aws_secret_key",
        regex=re.compile(
            r"(?i)aws_secret_access_key[\"\s:=]+([a-zA-Z0-9/+=]{40})"
        ),
        paranoid_only=False,
        description="AWS secret access key (value group only)",
    ),
    Pattern(
        name="github_fine_grained_pat",
        regex=re.compile(r"github_pat_[a-zA-Z0-9_]{82}"),
        paranoid_only=False,
        description="GitHub fine-grained personal access token",
    ),
    Pattern(
        name="github_pat",
        regex=re.compile(r"ghp_[a-zA-Z0-9]{36}"),
        paranoid_only=False,
        description="GitHub classic personal access token",
    ),
    Pattern(
        name="slack_token",
        regex=re.compile(r"xox[bpoa]-[a-zA-Z0-9-]{10,}"),
        paranoid_only=False,
        description="Slack token",
    ),
    Pattern(
        name="stripe_live_key",
        regex=re.compile(r"sk_live_[a-zA-Z0-9]{24,}"),
        paranoid_only=False,
        description="Stripe live secret key",
    ),
    Pattern(
        name="jwt",
        regex=re.compile(
            r"eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+"
        ),
        paranoid_only=False,
        description="JSON Web Token (3-segment base64url)",
    ),
    Pattern(
        name="database_connection",
        regex=re.compile(
            r"(?i)(?:postgres|postgresql|mysql|mongodb|redis)://"
            r"[^:\s]+:[^@\s]+@[^/\s]+"
        ),
        paranoid_only=False,
        description="Database connection string with embedded credentials",
    ),
    Pattern(
        name="private_ssh_key",
        regex=re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
        ),
        paranoid_only=False,
        description="PEM private key header",
    ),
    Pattern(
        name="generic_secret_assignment",
        regex=re.compile(
            r"(?i)(?:password|secret|api_key|access_key|auth_token)\s*[:=]\s*"
            r"[\"']?([a-zA-Z0-9+/=_-]{16,})[\"']?"
        ),
        paranoid_only=False,
        description="Secret-shaped key/value assignment (value group only)",
    ),
)


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


def _match_span(pattern: Pattern, match: re.Match[str]) -> tuple[int, int]:
    if pattern.name in _VALUE_GROUP_PATTERNS and match.lastindex:
        start, end = match.span(1)
        if start >= 0:
            return start, end
    return match.span()


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _format_location(prefix: str, line: int | None) -> str:
    if line is None:
        return prefix
    if not prefix:
        return f"line {line}"
    return f"{prefix}:line {line}"


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
    if not text:
        return RedactionResult(text=text, redactions=[])

    has_newlines = "\n" in text

    candidates: list[tuple[int, int, int, Pattern]] = []
    for idx, pattern in enumerate(PATTERNS):
        if pattern.paranoid_only and not paranoid:
            continue
        for match in pattern.regex.finditer(text):
            if pattern.name == "high_entropy" and (
                _shannon_entropy(match.group(0)) < ENTROPY_THRESHOLD
            ):
                continue
            start, end = _match_span(pattern, match)
            candidates.append((start, end, idx, pattern))

    # Sort by (start, end, pattern declaration order) so earlier patterns
    # win at equal spans, and lower-index matches always come first.
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    accepted: list[tuple[int, int, Pattern]] = []
    last_end = -1
    for start, end, _idx, pattern in candidates:
        if start < last_end:
            continue
        accepted.append((start, end, pattern))
        last_end = end

    if not accepted:
        return RedactionResult(text=text, redactions=[])

    out_parts: list[str] = []
    redactions: list[Redaction] = []
    cursor = 0
    for start, end, pattern in accepted:
        out_parts.append(text[cursor:start])
        out_parts.append(PLACEHOLDER_TEMPLATE.format(name=pattern.name))
        line = _line_for_offset(text, start) if has_newlines else None
        redactions.append(
            Redaction(
                category=pattern.name,
                location=_format_location(location_prefix, line),
                span=(start, end),
            )
        )
        cursor = end
    out_parts.append(text[cursor:])
    return RedactionResult(text="".join(out_parts), redactions=redactions)
