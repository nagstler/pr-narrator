"""Discover Claude Code session JSONL files on disk."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pr_narrator.errors import AmbiguousMatchError, SessionNotFoundError


@dataclass(frozen=True)
class SessionMeta:
    """Metadata for a single Claude Code session JSONL file."""

    session_id: str
    path: Path
    mtime: datetime
    size_bytes: int


def get_projects_dir() -> Path:
    """Return the path to ``~/.claude/projects/``, expanded."""
    return Path.home() / ".claude" / "projects"


def encode_cwd(cwd: Path) -> str:
    """Convert ``/Users/foo/bar`` to ``-Users-foo-bar``."""
    return str(cwd).replace("/", "-")


def project_dir_for_cwd(cwd: Path) -> Path:
    """Return the encoded projects subdir for a given working directory."""
    return get_projects_dir() / encode_cwd(cwd)


def _session_meta_from_path(path: Path) -> SessionMeta:
    stat = path.stat()
    return SessionMeta(
        session_id=path.stem,
        path=path,
        mtime=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        size_bytes=stat.st_size,
    )


def list_sessions(cwd: Path | None = None) -> list[SessionMeta]:
    """Return session JSONL files for ``cwd`` (default: current dir), newest first.

    Returns an empty list if the project directory does not exist.
    """
    target_cwd = cwd if cwd is not None else Path.cwd()
    proj_dir = project_dir_for_cwd(target_cwd)
    if not proj_dir.is_dir():
        return []
    sessions = [_session_meta_from_path(p) for p in proj_dir.glob("*.jsonl") if p.is_file()]
    sessions.sort(key=lambda s: s.mtime, reverse=True)
    return sessions


def find_latest_session(cwd: Path | None = None) -> SessionMeta | None:
    """Return the most recently modified session for ``cwd``, or ``None``."""
    sessions = list_sessions(cwd)
    return sessions[0] if sessions else None


def find_session_by_id(session_id: str, cwd: Path | None = None) -> SessionMeta:
    """Return the session whose UUID starts with ``session_id``.

    Raises:
        SessionNotFoundError: if no session matches the prefix.
        AmbiguousMatchError: if more than one session matches the prefix.
    """
    sessions = list_sessions(cwd)
    matches = [s for s in sessions if s.session_id.startswith(session_id)]
    if not matches:
        raise SessionNotFoundError(f"No Claude Code session matching prefix {session_id!r}")
    if len(matches) > 1:
        ids = ", ".join(s.session_id for s in matches)
        raise AmbiguousMatchError(f"Prefix {session_id!r} matches {len(matches)} sessions: {ids}")
    return matches[0]
