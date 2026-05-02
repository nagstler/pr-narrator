"""Tests for the redaction layer."""

from __future__ import annotations

import secrets

import pytest

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


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("key=sk-ant-" + "A" * 40 + " trailing", "anthropic_api_key"),
        ("key=sk-" + "A" * 48 + " trailing", "openai_api_key"),
        ("key=sk-proj-" + "A" * 40 + " trailing", "openai_project_key"),
        ("AKIAABCDEFGHIJKLMNOP rest", "aws_access_key"),
        ('aws_secret_access_key = "' + "A" * 40 + '"', "aws_secret_key"),
        ("token ghp_" + "a" * 36 + " end", "github_pat"),
        ("token github_pat_" + "a" * 82 + " end", "github_fine_grained_pat"),
        ("xoxb-" + "1" * 20 + " end", "slack_token"),
        ("sk_live_" + "1" * 30 + " end", "stripe_live_key"),
        ("eyJabc.eyJxyz.signature_part_here end", "jwt"),
        ("postgres://user:pass@host:5432/db", "database_connection"),
        ("-----BEGIN RSA PRIVATE KEY-----", "private_ssh_key"),
        ('password = "supersecret_value_12345"', "generic_secret_assignment"),
    ],
)
def test_conservative_pattern_matches(text: str, category: str) -> None:
    result = redact(text)
    cats = {r.category for r in result.redactions}
    assert category in cats, f"expected {category} in {cats} for {text!r}"
    assert "[REDACTED:" + category + "]" in result.text


@pytest.mark.parametrize(
    "text",
    [
        "sk-ant-shortlessthan40",
        "sk-only-23-chars-here-abc",
        "sk-proj-tooShort",
        "AKIAtoolow",
        "aws_secret_access_key=short",
        "ghp_too_short",
        "github_pat_too_short",
        "xoxb-shor",
        "sk_live_short",
        "eyJ.notajwt",
        "postgres://nobody",
        "BEGIN PRIVATE KEY no dashes",
        "the AKIA constant has 4 letters",
    ],
)
def test_conservative_pattern_does_not_false_positive(text: str) -> None:
    result = redact(text)
    assert result.redactions == [], (
        f"unexpected redactions {result.redactions} for {text!r}"
    )
    assert result.text == text
