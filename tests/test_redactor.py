"""Tests for the redaction layer."""

from __future__ import annotations

import secrets

from pr_narrator.redactor import (
    PATTERNS,
    Pattern,
    Redaction,
    RedactionResult,
    _shannon_entropy,
    redact,
)


def test_module_exports_public_surface() -> None:
    assert callable(redact)
    assert isinstance(PATTERNS, tuple)
    assert all(isinstance(p, Pattern) for p in PATTERNS)
    # Result types are referenced by callers; ensure the constructors work.
    r = Redaction(category="x", location="y", span=(0, 1))
    assert r.category == "x"
    rr = RedactionResult(text="x", redactions=[])
    assert rr.text == "x"


def test_entropy_low_for_repeated_char() -> None:
    assert _shannon_entropy("aaaaaaaa") == 0.0


def test_entropy_low_for_english() -> None:
    assert _shannon_entropy("hello world") < 4.0


def test_entropy_high_for_random_token() -> None:
    token = secrets.token_urlsafe(32)
    assert _shannon_entropy(token) >= 4.5


def test_entropy_empty_string_returns_zero() -> None:
    assert _shannon_entropy("") == 0.0
