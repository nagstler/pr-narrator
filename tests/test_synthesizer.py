"""Tests for the LLM synthesis layer. Subprocess always mocked."""

from __future__ import annotations

import json
import subprocess
from decimal import Decimal
from unittest.mock import patch

import pytest

from pr_narrator.compressor import CompressedEntry, CompressedTranscript
from pr_narrator.errors import ClaudeBinaryNotFoundError, SynthesisError
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
