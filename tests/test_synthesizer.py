"""Tests for the LLM synthesis layer. Subprocess always mocked."""

from __future__ import annotations

import json
import subprocess
from decimal import Decimal
from unittest.mock import patch

import pytest

from pr_narrator.compressor import CompressedEntry, CompressedTranscript
from pr_narrator.errors import ClaudeBinaryNotFoundError, SynthesisError
from pr_narrator.redactor import Redaction
from pr_narrator.synthesizer import (
    SynthesisResult,
    synthesize_pr_description,
)


def _compressed() -> CompressedTranscript:
    return CompressedTranscript(
        timeline=[CompressedEntry(timestamp_offset=0, kind="user", text="hi")],
        tool_call_summary={"Edit": 1},
        user_intent_chain=["hi"],
        duration_seconds=10,
        meta={},
    )


def _make_completed(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _valid_response() -> str:
    body = (
        "<!-- pr-narrator-meta\n"
        "change_type: feat\n"
        "scope: synthesizer\n"
        "risk_level: low\n"
        "files_touched: 5\n"
        "considered_alternatives: false\n"
        "-->\n"
        "\n"
        "## What changed\n"
        "Added the synthesis layer.\n"
    )
    return json.dumps(
        {
            "result": body,
            "cost_usd": 0.0234,
            "model": "claude-sonnet-4-7",
            "is_error": False,
        }
    )


def test_happy_path_parses_frontmatter_and_body() -> None:
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=_valid_response()),
    ) as mock_run:
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="diff --git a/x b/x\n",
            changed_files=["x"],
            commit_messages=["feat: x"],
            branch="feat/x",
        )

    assert isinstance(result, SynthesisResult)
    assert result.frontmatter == {
        "change_type": "feat",
        "scope": "synthesizer",
        "risk_level": "low",
        "files_touched": 5,
        "considered_alternatives": False,
    }
    assert result.frontmatter_complete is True
    assert "## What changed" in result.markdown
    assert result.cost_estimate_usd == Decimal("0.0234")
    assert result.model == "claude-sonnet-4-7"

    args, kwargs = mock_run.call_args
    argv = args[0]
    assert "--output-format" in argv and "json" in argv
    assert "--no-session-persistence" in argv
    assert "--tools" in argv
    assert "--system-prompt" in argv
    assert "--model" in argv
    assert kwargs["input"]


def test_change_type_normalization_feature_to_feat() -> None:
    body = "<!-- pr-narrator-meta\nchange_type: feature\nrisk_level: medium\n-->\n## body\n"
    response = json.dumps({"result": body})
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    assert result.frontmatter is not None
    assert result.frontmatter["change_type"] == "feat"
    assert result.frontmatter["risk_level"] == "medium"
    assert result.frontmatter_complete is True


def test_int_and_bool_coercion() -> None:
    body = (
        "<!-- pr-narrator-meta\n"
        "change_type: fix\n"
        "risk_level: low\n"
        "files_touched: 7\n"
        "considered_alternatives: TRUE\n"
        "-->\n"
        "body\n"
    )
    response = json.dumps({"result": body})
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    assert result.frontmatter is not None
    assert result.frontmatter["files_touched"] == 7
    assert result.frontmatter["considered_alternatives"] is True


def test_invalid_files_touched_silently_dropped() -> None:
    body = (
        "<!-- pr-narrator-meta\n"
        "change_type: fix\n"
        "risk_level: low\n"
        "files_touched: not-a-number\n"
        "-->\n"
        "body\n"
    )
    response = json.dumps({"result": body})
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    assert result.frontmatter is not None
    assert "files_touched" not in result.frontmatter
    assert result.frontmatter_complete is True  # required keys still valid


def test_invalid_considered_alternatives_silently_dropped() -> None:
    body = (
        "<!-- pr-narrator-meta\n"
        "change_type: fix\n"
        "risk_level: low\n"
        "considered_alternatives: maybe\n"
        "-->\n"
        "body\n"
    )
    response = json.dumps({"result": body})
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    assert result.frontmatter is not None
    assert "considered_alternatives" not in result.frontmatter


def test_missing_required_key_drops_to_tier3() -> None:
    body = "<!-- pr-narrator-meta\nscope: foo\n-->\n## body\n"
    response = json.dumps({"result": body})
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    assert result.frontmatter is None
    assert result.frontmatter_complete is False


def test_no_frontmatter_at_all_drops_to_tier3() -> None:
    response = json.dumps({"result": "no frontmatter at all\n## body\n"})
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    assert result.frontmatter is None
    assert result.frontmatter_complete is False


def test_unclosed_frontmatter_treated_as_missing() -> None:
    body = "<!-- pr-narrator-meta\nchange_type: feat\nrisk_level: low\n## body\n"
    response = json.dumps({"result": body})
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    assert result.frontmatter is None


def test_strict_mode_rejects_tier3() -> None:
    response = json.dumps({"result": "no frontmatter at all"})
    with (
        patch(
            "pr_narrator.synthesizer.subprocess.run",
            return_value=_make_completed(stdout=response),
        ),
        pytest.raises(SynthesisError),
    ):
        synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
            strict=True,
        )


def test_strict_mode_succeeds_on_tier1() -> None:
    response = _valid_response()
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
            strict=True,
        )
    assert result.frontmatter_complete is True


def test_malformed_json_raises_synthesis_error() -> None:
    with (
        patch(
            "pr_narrator.synthesizer.subprocess.run",
            return_value=_make_completed(stdout="not json"),
        ),
        pytest.raises(SynthesisError),
    ):
        synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )


def test_non_object_json_raises_synthesis_error() -> None:
    with (
        patch(
            "pr_narrator.synthesizer.subprocess.run",
            return_value=_make_completed(stdout="[1,2,3]"),
        ),
        pytest.raises(SynthesisError),
    ):
        synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )


def test_is_error_true_raises_synthesis_error_with_subtype() -> None:
    response = json.dumps({"result": "x", "is_error": True, "subtype": "rate_limit"})
    with (
        patch(
            "pr_narrator.synthesizer.subprocess.run",
            return_value=_make_completed(stdout=response),
        ),
        pytest.raises(SynthesisError, match="rate_limit"),
    ):
        synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )


def test_is_error_true_without_subtype_uses_unknown() -> None:
    response = json.dumps({"result": "x", "is_error": True})
    with (
        patch(
            "pr_narrator.synthesizer.subprocess.run",
            return_value=_make_completed(stdout=response),
        ),
        pytest.raises(SynthesisError, match="unknown"),
    ):
        synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )


def test_missing_result_field_raises_synthesis_error() -> None:
    response = json.dumps({"cost_usd": 0.01})
    with (
        patch(
            "pr_narrator.synthesizer.subprocess.run",
            return_value=_make_completed(stdout=response),
        ),
        pytest.raises(SynthesisError),
    ):
        synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )


def test_empty_result_string_raises_synthesis_error() -> None:
    response = json.dumps({"result": "   "})
    with (
        patch(
            "pr_narrator.synthesizer.subprocess.run",
            return_value=_make_completed(stdout=response),
        ),
        pytest.raises(SynthesisError),
    ):
        synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )


def test_timeout_raises_synthesis_error() -> None:
    with (
        patch(
            "pr_narrator.synthesizer.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120),
        ),
        pytest.raises(SynthesisError, match="timed out"),
    ):
        synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )


def test_claude_binary_not_found_raises_typed_error() -> None:
    with (
        patch("pr_narrator.synthesizer.subprocess.run", side_effect=FileNotFoundError),
        pytest.raises(ClaudeBinaryNotFoundError),
    ):
        synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )


def test_non_zero_exit_raises_synthesis_error() -> None:
    with (
        patch(
            "pr_narrator.synthesizer.subprocess.run",
            return_value=_make_completed(stderr="boom", returncode=2),
        ),
        pytest.raises(SynthesisError, match="boom"),
    ):
        synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )


def test_to_dict_serializes_decimal_and_datetime() -> None:
    response = _valid_response()
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    d = result.to_dict()
    s = json.dumps(d)
    rehydrated = json.loads(s)
    assert rehydrated["cost_estimate_usd"] == "0.0234"
    assert isinstance(rehydrated["synthesized_at"], str)


def test_to_dict_handles_none_cost() -> None:
    response = json.dumps({"result": "no frontmatter\nbody"})
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    d = result.to_dict()
    assert d["cost_estimate_usd"] is None


def test_empty_frontmatter_block_drops_to_tier3() -> None:
    body = "<!-- pr-narrator-meta\n   \n-->\n## body\n"
    response = json.dumps({"result": body})
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    assert result.frontmatter is None
    assert result.frontmatter_complete is False


def test_invalid_risk_level_drops_to_tier3() -> None:
    body = "<!-- pr-narrator-meta\nchange_type: feat\nrisk_level: bogus\n-->\n## body\n"
    response = json.dumps({"result": body})
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    assert result.frontmatter is None


def test_unparseable_cost_silently_drops_to_none() -> None:
    body = "<!-- pr-narrator-meta\nchange_type: feat\nrisk_level: low\n-->\n## body\n"
    response = json.dumps({"result": body, "cost_usd": "abc"})
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    assert result.cost_estimate_usd is None


def test_frontmatter_line_with_empty_key_skipped() -> None:
    # Line ": value" partitions to (key="", sep=":", value="value")
    body = (
        "<!-- pr-narrator-meta\n"
        "change_type: feat\n"
        ": orphan_value_no_key\n"
        "risk_level: low\n"
        "-->\n## body\n"
    )
    response = json.dumps({"result": body})
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    assert result.frontmatter is not None
    assert result.frontmatter["change_type"] == "feat"
    assert result.frontmatter["risk_level"] == "low"


def test_response_model_falls_back_to_request_model() -> None:
    body = "<!-- pr-narrator-meta\nchange_type: feat\nrisk_level: low\n-->\n## body\n"
    response = json.dumps({"result": body})  # no `model` field
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=response),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
            model="opus",
        )
    assert result.model == "opus"


# ---------------------------------------------------------------------------
# Redaction integration
# ---------------------------------------------------------------------------


_SECRET = "sk-ant-" + "A" * 60


def _compressed_with_secret() -> CompressedTranscript:
    return CompressedTranscript(
        timeline=[
            CompressedEntry(timestamp_offset=0, kind="user", text="hi"),
            CompressedEntry(
                timestamp_offset=10, kind="user", text=f"the key is {_SECRET}"
            ),
        ],
        tool_call_summary={"Edit": 1},
        user_intent_chain=["hi", f"the key is {_SECRET}"],
        duration_seconds=10,
        meta={},
    )


def test_input_redaction_strips_secret_before_prompt() -> None:
    diff_with_secret = (
        "diff --git a/.env b/.env\n"
        "--- a/.env\n"
        "+++ b/.env\n"
        "@@ -1 +1 @@\n"
        f"+API_KEY={_SECRET}\n"
    )
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=_valid_response()),
    ) as mock_run:
        result = synthesize_pr_description(
            compressed=_compressed_with_secret(),
            diff=diff_with_secret,
            changed_files=[".env"],
            commit_messages=["feat: x"],
            branch="feat/x",
        )

    sent_input = mock_run.call_args.kwargs["input"]
    assert _SECRET not in sent_input
    assert "[REDACTED:anthropic_api_key]" in sent_input
    cats = {r.category for r in result.redactions}
    assert "anthropic_api_key" in cats
    # Both the user_intent_chain hit and the diff hit should be reported.
    locs = [r.location for r in result.redactions]
    assert any(loc.startswith("user_intent_chain[") for loc in locs)
    assert any(loc.startswith("diff:.env") for loc in locs)


def test_redactions_serialized_in_to_dict() -> None:
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=_valid_response()),
    ):
        result = synthesize_pr_description(
            compressed=_compressed_with_secret(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    d = result.to_dict()
    assert isinstance(d["redactions"], list)
    assert d["redactions"]
    sample = d["redactions"][0]
    assert {"category", "location", "span"} <= set(sample.keys())
    assert isinstance(sample["span"], list)
    assert len(sample["span"]) == 2
    # Round-trips through JSON.
    rehydrated = json.loads(json.dumps(d))
    assert rehydrated["redactions"][0]["category"] == sample["category"]


def test_truncation_note_records_redactions() -> None:
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=_valid_response()),
    ):
        result = synthesize_pr_description(
            compressed=_compressed_with_secret(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    notes = " ".join(result.truncation_notes)
    assert "Redacted" in notes
    assert "anthropic_api_key" in notes


def test_no_redactions_means_empty_list_and_no_note() -> None:
    """Clean input doesn't add a redaction note."""
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=_valid_response()),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    assert result.redactions == []
    assert all("Redacted" not in n for n in result.truncation_notes)


def test_output_redaction_catches_llm_regurgitated_secret() -> None:
    leaked = "sk-ant-" + "B" * 60
    body = (
        "<!-- pr-narrator-meta\n"
        "change_type: feat\nrisk_level: low\n-->\n"
        f"## leaked\nthe key was {leaked}\n"
    )
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=json.dumps({"result": body})),
    ):
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    assert leaked not in result.markdown
    assert "[REDACTED:anthropic_api_key]" in result.markdown
    assert any(
        r.location.startswith("output") and r.category == "anthropic_api_key"
        for r in result.redactions
    )


def test_paranoid_flag_enables_paranoid_patterns_in_input() -> None:
    transcript = CompressedTranscript(
        timeline=[
            CompressedEntry(
                timestamp_offset=0,
                kind="user",
                text="working in /Users/alice/work/repo",
            )
        ],
        tool_call_summary={},
        user_intent_chain=["working in /Users/alice/work/repo"],
        duration_seconds=0,
        meta={},
    )

    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=_valid_response()),
    ) as mock_run:
        result = synthesize_pr_description(
            compressed=transcript,
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
            paranoid=True,
        )
    sent = mock_run.call_args.kwargs["input"]
    assert "/Users/alice/" not in sent
    assert any(r.category == "home_path_macos" for r in result.redactions)


def test_paranoid_off_does_not_redact_home_paths() -> None:
    transcript = CompressedTranscript(
        timeline=[],
        tool_call_summary={},
        user_intent_chain=["working in /Users/alice/work/repo"],
        duration_seconds=0,
        meta={},
    )
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=_valid_response()),
    ) as mock_run:
        synthesize_pr_description(
            compressed=transcript,
            diff="",
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    sent = mock_run.call_args.kwargs["input"]
    assert "/Users/alice/work/repo" in sent


def test_diff_with_no_parseable_blocks_falls_through_to_whole_blob_redaction() -> None:
    """A non-empty diff whose split yields no usable file blocks (e.g.
    whitespace only) falls through to whole-blob redaction. Covers the
    defensive branch in _redact_inputs.
    """
    diff_blob = "   \n   \n"  # truthy but parse_diff_into_files returns []
    with patch(
        "pr_narrator.synthesizer.subprocess.run",
        return_value=_make_completed(stdout=_valid_response()),
    ) as mock_run:
        result = synthesize_pr_description(
            compressed=_compressed(),
            diff=diff_blob,
            changed_files=[],
            commit_messages=[],
            branch="b",
        )
    sent = mock_run.call_args.kwargs["input"]
    assert isinstance(sent, str)
    # Nothing to redact, but the else branch executed without error.
    assert all(not r.location.startswith("diff:") for r in result.redactions)


def test_redactions_field_default_is_empty_list() -> None:
    """The Redaction dataclass field defaults to an empty list, not None."""
    result = SynthesisResult(
        markdown="x",
        frontmatter=None,
        frontmatter_complete=False,
        raw_response="",
        prompt="",
        model="sonnet",
        cost_estimate_usd=None,
    )
    assert result.redactions == []
    # Sanity: the type carries through to_dict.
    assert result.to_dict()["redactions"] == []
    _ = Redaction  # imported for type-check; used in cli tests too.
