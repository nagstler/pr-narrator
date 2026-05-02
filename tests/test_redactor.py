"""Tests for the redaction layer."""

from __future__ import annotations

from pr_narrator.redactor import (
    PATTERNS,
    Pattern,
    Redaction,
    RedactionResult,
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
