"""Wrappers around `gh` and `git push` / `git ls-remote` for PR creation."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Literal

from pr_narrator.errors import (
    GitHubCliNotFoundError,
    PRCreationError,
    PushFailedError,
)

PRState = Literal["OPEN", "CLOSED", "MERGED"]


@dataclass(frozen=True)
class PRInfo:
    number: int
    state: PRState
    url: str


def _run_gh(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["gh", *args],
            check=False,
            capture_output=True,
            text=True,
            input=input_text,
        )
    except FileNotFoundError as exc:
        raise GitHubCliNotFoundError(
            "GitHub CLI (`gh`) is not installed or not on PATH. "
            "Install from https://cli.github.com/ and run `gh auth login`."
        ) from exc


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def get_remote_pr_for_branch(branch: str) -> PRInfo | None:
    """Return the most recent PR for `branch`, or None if none exist."""
    completed = _run_gh(
        [
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "all",
            "--json",
            "number,state,url",
        ]
    )
    if completed.returncode != 0:
        raise PRCreationError(
            f"gh pr list failed (exit {completed.returncode}): {completed.stderr.strip()}"
        )
    try:
        data = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise PRCreationError(
            f"gh pr list returned non-JSON output: {completed.stdout[:200]}"
        ) from exc

    if not isinstance(data, list) or not data:
        return None

    most_recent = max(data, key=lambda item: int(item.get("number", 0)))
    state = most_recent.get("state", "")
    if state not in ("OPEN", "CLOSED", "MERGED"):
        raise PRCreationError(f"gh pr list returned unexpected state: {state!r}")
    return PRInfo(
        number=int(most_recent["number"]),
        state=state,
        url=str(most_recent["url"]),
    )


def push_branch(branch: str, remote: str = "origin") -> None:
    """Run `git push --set-upstream <remote> <branch>`."""
    completed = _run_git(["push", "--set-upstream", remote, branch])
    if completed.returncode != 0:
        raise PushFailedError(
            f"git push failed (exit {completed.returncode}): {completed.stderr.strip()}"
        )


def create_pr(
    title: str,
    body: str,
    base: str = "main",
    draft: bool = True,
) -> str:
    """Open a PR via `gh pr create`. Body passed on stdin to avoid escaping issues."""
    args = [
        "pr",
        "create",
        "--base",
        base,
        "--title",
        title,
        "--body-file",
        "-",
    ]
    if draft:
        args.append("--draft")
    completed = _run_gh(args, input_text=body)
    if completed.returncode != 0:
        raise PRCreationError(
            f"gh pr create failed (exit {completed.returncode}): {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def is_branch_on_remote(branch: str, remote: str = "origin") -> bool:
    """Empty `git ls-remote` output means the branch is not on remote."""
    completed = _run_git(["ls-remote", "--heads", remote, branch])
    return bool(completed.stdout.strip())
