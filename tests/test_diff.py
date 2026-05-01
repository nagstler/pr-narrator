"""Tests for git diff utilities. All subprocess calls mocked."""

from __future__ import annotations

import subprocess
from contextlib import AbstractContextManager
from unittest.mock import patch

import pytest

from pr_narrator.diff import (
    get_branch_diff,
    get_changed_files,
    get_commit_messages,
    get_current_branch,
)
from pr_narrator.errors import NotInGitRepoError, UnknownBaseRefError


def _mock_run(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> AbstractContextManager[object]:
    completed = subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=stderr
    )
    return patch("pr_narrator.diff.subprocess.run", return_value=completed)


def test_get_branch_diff_uses_three_dot_syntax() -> None:
    with _mock_run(stdout="diff --git a/x b/x\n") as mock:
        result = get_branch_diff(base="develop")
    assert result == "diff --git a/x b/x\n"
    args, _ = mock.call_args
    assert args[0] == ["git", "diff", "develop...HEAD"]


def test_get_changed_files_returns_list() -> None:
    with _mock_run(stdout="a.py\nb.py\n\nc.py\n"):
        result = get_changed_files()
    assert result == ["a.py", "b.py", "c.py"]


def test_get_commit_messages_filters_empty_strings() -> None:
    with _mock_run(stdout="feat: a\nfix: b\n"):
        result = get_commit_messages()
    assert result == ["feat: a", "fix: b"]


def test_get_commit_messages_empty_log_returns_empty_list() -> None:
    with _mock_run(stdout=""):
        result = get_commit_messages()
    assert result == []


def test_get_current_branch_strips_newline() -> None:
    with _mock_run(stdout="feat/synthesizer\n"):
        result = get_current_branch()
    assert result == "feat/synthesizer"


def test_git_not_installed_raises_not_in_git_repo() -> None:
    with (
        patch("pr_narrator.diff.subprocess.run", side_effect=FileNotFoundError),
        pytest.raises(NotInGitRepoError),
    ):
        get_branch_diff()


def test_not_a_git_repo_raises_not_in_git_repo() -> None:
    with (
        _mock_run(
            stderr="fatal: not a git repository (or any parent up to mount point /)",
            returncode=128,
        ),
        pytest.raises(NotInGitRepoError),
    ):
        get_branch_diff()


def test_unknown_revision_raises_unknown_base_ref() -> None:
    with (
        _mock_run(
            stderr="fatal: ambiguous argument 'nonexistent...HEAD': unknown revision",
            returncode=128,
        ),
        pytest.raises(UnknownBaseRefError),
    ):
        get_branch_diff(base="nonexistent")


def test_bad_revision_raises_unknown_base_ref() -> None:
    with (
        _mock_run(stderr="fatal: bad revision 'asdf'", returncode=128),
        pytest.raises(UnknownBaseRefError),
    ):
        get_branch_diff(base="asdf")


def test_other_git_failure_raises_runtime_error() -> None:
    with (
        _mock_run(stderr="some other unexpected error", returncode=1),
        pytest.raises(RuntimeError),
    ):
        get_branch_diff()
