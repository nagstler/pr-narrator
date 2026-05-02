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
    # token_urlsafe(64) is empirically always >= 4.5 entropy across thousands
    # of samples; (32) flakes ~0.5% of the time.
    token = secrets.token_urlsafe(64)
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
    assert result.redactions == [], f"unexpected redactions {result.redactions} for {text!r}"
    assert result.text == text


_PARANOID_CATEGORIES = {
    "high_entropy",
    "env_assignment",
    "home_path_macos",
    "home_path_linux",
    "email",
    "private_ipv4",
}


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("a high entropy " + secrets.token_urlsafe(64) + " trail", "high_entropy"),
        ("API_TOKEN=Z9q83hd83js9fjs0\n", "env_assignment"),
        ("/Users/alice/foo/bar", "home_path_macos"),
        ("/home/alice/foo/bar", "home_path_linux"),
        ("contact alice@example.com today", "email"),
        ("server is at 192.168.1.10 today", "private_ipv4"),
        ("server is at 10.0.0.5 today", "private_ipv4"),
        ("server is at 172.16.5.10 today", "private_ipv4"),
    ],
)
def test_paranoid_pattern_matches_only_when_enabled(text: str, category: str) -> None:
    off = redact(text, paranoid=False)
    assert all(r.category != category for r in off.redactions)

    on = redact(text, paranoid=True)
    cats = {r.category for r in on.redactions}
    assert category in cats, f"expected {category} in {cats} for {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        "shortwordcount",
        "FOO=bar",
        "/Users",
        "/home",
        "not_an_email",
        "server is at 8.8.8.8 today",
        "version 1.2.3.4 is fine",
    ],
)
def test_paranoid_negatives(text: str) -> None:
    result = redact(text, paranoid=True)
    assert all(r.category not in _PARANOID_CATEGORIES for r in result.redactions), (
        f"unexpected paranoid redaction: {result.redactions}"
    )


def test_high_entropy_skips_low_entropy_run() -> None:
    text = "value=" + ("a" * 32)
    result = redact(text, paranoid=True)
    assert all(r.category != "high_entropy" for r in result.redactions)


def test_location_prefix_concatenated() -> None:
    text = "key=sk-ant-" + "A" * 50
    result = redact(text, location_prefix="user_intent_chain[2]")
    assert len(result.redactions) == 1
    assert result.redactions[0].location == "user_intent_chain[2]"


def test_location_includes_line_for_multiline() -> None:
    text = "first\nkey=sk-ant-" + "A" * 50 + "\nthird"
    result = redact(text, location_prefix="diff:src/config.py")
    assert result.redactions[0].location == "diff:src/config.py:line 2"


def test_location_no_prefix_with_line() -> None:
    text = "first\nkey=sk-ant-" + "A" * 50 + "\nthird"
    result = redact(text)
    assert result.redactions[0].location == "line 2"


def test_multiple_redactions_in_one_input() -> None:
    text = "first sk-ant-" + "A" * 50 + " then ghp_" + "x" * 36 + " plus AKIAABCDEFGHIJKLMNOP"
    result = redact(text)
    cats = [r.category for r in result.redactions]
    assert cats == ["anthropic_api_key", "github_pat", "aws_access_key"]
    assert result.text.count("[REDACTED:") == 3


def test_overlap_first_match_wins() -> None:
    # Conservative anthropic pattern should win over paranoid high_entropy
    # on the same span.
    text = "sk-ant-" + "A" * 50
    result = redact(text, paranoid=True)
    assert len(result.redactions) == 1
    assert result.redactions[0].category == "anthropic_api_key"


def test_idempotent_on_already_redacted_text() -> None:
    text = "key=sk-ant-" + "A" * 50
    once = redact(text)
    twice = redact(once.text)
    assert twice.text == once.text
    assert twice.redactions == []


def test_empty_input_returns_empty_result() -> None:
    result = redact("")
    assert result.text == ""
    assert result.redactions == []


def test_no_match_returns_text_unchanged() -> None:
    result = redact("plain prose with no secrets in it.", paranoid=True)
    assert result.text == "plain prose with no secrets in it."
    assert result.redactions == []


def test_redactions_are_in_span_order() -> None:
    text = "ghp_" + "x" * 36 + " then sk-ant-" + "A" * 50
    result = redact(text)
    spans = [r.span for r in result.redactions]
    assert spans == sorted(spans)
