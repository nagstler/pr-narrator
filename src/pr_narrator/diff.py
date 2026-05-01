"""Capture the current git state for synthesis: diff, files, commits, branch."""

from __future__ import annotations

import subprocess

from pr_narrator.errors import NotInGitRepoError, UnknownBaseRefError


def _run_git(args: list[str]) -> str:
    """Invoke git, mapping common failure shapes to typed exceptions."""
    try:
        result = subprocess.run(
            ["git", *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise NotInGitRepoError("git executable not found on PATH") from exc

    if result.returncode == 0:
        return result.stdout

    stderr = result.stderr.lower()
    if "not a git repository" in stderr:
        raise NotInGitRepoError(result.stderr.strip())
    if "unknown revision" in stderr or "bad revision" in stderr:
        raise UnknownBaseRefError(result.stderr.strip())
    raise RuntimeError(
        f"git {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}"
    )


def get_branch_diff(base: str = "main") -> str:
    """Return `git diff <base>...HEAD` (three-dot, branch-only)."""
    return _run_git(["diff", f"{base}...HEAD"])


def get_changed_files(base: str = "main") -> list[str]:
    """Return list of files changed on the branch vs base."""
    out = _run_git(["diff", "--name-only", f"{base}...HEAD"])
    return [line for line in out.splitlines() if line]


def get_commit_messages(base: str = "main") -> list[str]:
    """Return commit subjects reachable from HEAD but not from base."""
    out = _run_git(["log", f"{base}..HEAD", "--pretty=format:%s"])
    return [line for line in out.splitlines() if line]


def get_current_branch() -> str:
    """Return the current branch name (rstrip newline)."""
    return _run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
