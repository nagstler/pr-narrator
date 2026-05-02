"""Tests for the gh CLI wrapper. Subprocess always mocked."""

from __future__ import annotations

import json
import subprocess
from contextlib import AbstractContextManager
from unittest.mock import patch

import pytest

from pr_narrator.errors import (
    GitHubCliNotFoundError,
    PRCreationError,
    PushFailedError,
)
from pr_narrator.github import (
    PRInfo,
    create_pr,
    get_remote_pr_for_branch,
    is_branch_on_remote,
    push_branch,
)


def _completed(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["dummy"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _mock_run(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> AbstractContextManager[object]:
    return patch(
        "pr_narrator.github.subprocess.run",
        return_value=_completed(stdout=stdout, stderr=stderr, returncode=returncode),
    )


# -- get_remote_pr_for_branch ------------------------------------------------


def test_get_remote_pr_returns_pr_info_on_match() -> None:
    payload = json.dumps([{"number": 42, "state": "OPEN", "url": "https://github.com/x/y/pull/42"}])
    with _mock_run(stdout=payload) as mock:
        result = get_remote_pr_for_branch("feat/x")
    assert result == PRInfo(number=42, state="OPEN", url="https://github.com/x/y/pull/42")
    args, _ = mock.call_args
    argv = args[0]
    assert argv[:2] == ["gh", "pr"]
    assert "list" in argv
    assert "--head" in argv
    assert "feat/x" in argv
    assert "--state" in argv
    assert "all" in argv
    assert "--json" in argv


def test_get_remote_pr_returns_none_on_empty_list() -> None:
    with _mock_run(stdout="[]"):
        assert get_remote_pr_for_branch("feat/x") is None


def test_get_remote_pr_returns_most_recent_on_multiple_matches() -> None:
    payload = json.dumps(
        [
            {"number": 7, "state": "MERGED", "url": "https://github.com/x/y/pull/7"},
            {"number": 42, "state": "OPEN", "url": "https://github.com/x/y/pull/42"},
            {"number": 19, "state": "CLOSED", "url": "https://github.com/x/y/pull/19"},
        ]
    )
    with _mock_run(stdout=payload):
        result = get_remote_pr_for_branch("feat/x")
    assert result is not None
    assert result.number == 42


def test_get_remote_pr_raises_github_cli_not_found_when_gh_missing() -> None:
    with (
        patch("pr_narrator.github.subprocess.run", side_effect=FileNotFoundError),
        pytest.raises(GitHubCliNotFoundError),
    ):
        get_remote_pr_for_branch("feat/x")


def test_get_remote_pr_raises_on_gh_nonzero_exit() -> None:
    with (
        _mock_run(stderr="boom", returncode=1),
        pytest.raises(PRCreationError) as exc,
    ):
        get_remote_pr_for_branch("feat/x")
    assert "boom" in str(exc.value)


def test_get_remote_pr_raises_on_non_json_output() -> None:
    with (
        _mock_run(stdout="not json {"),
        pytest.raises(PRCreationError) as exc,
    ):
        get_remote_pr_for_branch("feat/x")
    assert "non-JSON" in str(exc.value)


def test_get_remote_pr_raises_on_unexpected_state() -> None:
    payload = json.dumps([{"number": 1, "state": "DRAFT", "url": "https://github.com/x/y/pull/1"}])
    with (
        _mock_run(stdout=payload),
        pytest.raises(PRCreationError) as exc,
    ):
        get_remote_pr_for_branch("feat/x")
    assert "DRAFT" in str(exc.value)


# -- push_branch -------------------------------------------------------------


def test_push_branch_builds_correct_argv() -> None:
    with _mock_run() as mock:
        push_branch("feat/x")
    args, _ = mock.call_args
    assert args[0] == ["git", "push", "--set-upstream", "origin", "feat/x"]


def test_push_branch_raises_push_failed_on_nonzero() -> None:
    with (
        _mock_run(stderr="rejected: non-fast-forward", returncode=1),
        pytest.raises(PushFailedError) as exc,
    ):
        push_branch("feat/x")
    assert "rejected" in str(exc.value)


# -- create_pr ---------------------------------------------------------------


def test_create_pr_passes_body_on_stdin() -> None:
    with _mock_run(stdout="https://github.com/x/y/pull/99\n") as mock:
        url = create_pr(title="feat(cli): x", body="## Body\n", base="main", draft=True)
    assert url == "https://github.com/x/y/pull/99"
    args, kwargs = mock.call_args
    argv = args[0]
    assert argv[:3] == ["gh", "pr", "create"]
    assert "--base" in argv and "main" in argv
    assert "--title" in argv
    assert "feat(cli): x" in argv
    assert "--body-file" in argv and "-" in argv
    assert "--draft" in argv
    assert kwargs["input"] == "## Body\n"


def test_create_pr_omits_draft_flag_when_not_draft() -> None:
    with _mock_run(stdout="https://github.com/x/y/pull/100\n") as mock:
        create_pr(title="t", body="b", base="main", draft=False)
    args, _ = mock.call_args
    assert "--draft" not in args[0]


def test_create_pr_raises_on_nonzero() -> None:
    with (
        _mock_run(stderr="auth failed", returncode=1),
        pytest.raises(PRCreationError) as exc,
    ):
        create_pr(title="t", body="b")
    assert "auth failed" in str(exc.value)


def test_create_pr_raises_github_cli_not_found_when_gh_missing() -> None:
    with (
        patch("pr_narrator.github.subprocess.run", side_effect=FileNotFoundError),
        pytest.raises(GitHubCliNotFoundError),
    ):
        create_pr(title="t", body="b")


# -- is_branch_on_remote -----------------------------------------------------


def test_is_branch_on_remote_true_when_output_present() -> None:
    with _mock_run(stdout="abc123\trefs/heads/feat/x\n") as mock:
        assert is_branch_on_remote("feat/x") is True
    args, _ = mock.call_args
    assert args[0] == ["git", "ls-remote", "--heads", "origin", "feat/x"]


def test_is_branch_on_remote_false_when_empty() -> None:
    with _mock_run(stdout=""):
        assert is_branch_on_remote("feat/x") is False
