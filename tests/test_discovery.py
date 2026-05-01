"""Tests for pr_narrator.discovery."""

from __future__ import annotations

import os
from datetime import UTC
from pathlib import Path

import pytest

from pr_narrator.discovery import (
    SessionMeta,
    encode_cwd,
    find_latest_session,
    find_session_by_id,
    get_projects_dir,
    list_sessions,
    project_dir_for_cwd,
)
from pr_narrator.errors import AmbiguousMatchError, SessionNotFoundError


def test_get_projects_dir_is_under_home() -> None:
    result = get_projects_dir()
    assert result == Path.home() / ".claude" / "projects"


def test_encode_cwd_typical_path() -> None:
    assert encode_cwd(Path("/Users/foo/bar")) == "-Users-foo-bar"


def test_encode_cwd_root() -> None:
    assert encode_cwd(Path("/")) == "-"


def test_encode_cwd_preserves_spaces() -> None:
    assert encode_cwd(Path("/path/with spaces/x")) == "-path-with spaces-x"


def test_project_dir_for_cwd_combines_helpers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("pr_narrator.discovery.get_projects_dir", lambda: tmp_path / "projects")
    cwd = Path("/Users/foo/bar")
    assert project_dir_for_cwd(cwd) == tmp_path / "projects" / "-Users-foo-bar"


@pytest.fixture
def fake_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Set up a fake ~/.claude/projects/ with the cwd pointing at a fresh dir."""
    projects = tmp_path / "projects"
    fake_cwd = tmp_path / "myproj"
    fake_cwd.mkdir()
    monkeypatch.chdir(fake_cwd)
    monkeypatch.setattr("pr_narrator.discovery.get_projects_dir", lambda: projects)
    return projects, fake_cwd


def _make_session(proj_dir: Path, name: str, mtime_offset: float = 0.0) -> Path:
    proj_dir.mkdir(parents=True, exist_ok=True)
    p = proj_dir / f"{name}.jsonl"
    p.write_text('{"type":"user"}\n', encoding="utf-8")
    if mtime_offset:
        stat = p.stat()
        os.utime(p, (stat.st_atime, stat.st_mtime + mtime_offset))
    return p


def test_list_sessions_empty_when_no_project_dir(fake_env: tuple[Path, Path]) -> None:
    assert list_sessions() == []


def test_list_sessions_returns_session_meta(fake_env: tuple[Path, Path]) -> None:
    projects, cwd = fake_env
    proj_dir = projects / encode_cwd(cwd)
    _make_session(proj_dir, "abc12345-0000-0000-0000-000000000000")
    result = list_sessions()
    assert len(result) == 1
    assert isinstance(result[0], SessionMeta)
    assert result[0].session_id == "abc12345-0000-0000-0000-000000000000"
    assert result[0].size_bytes > 0
    assert result[0].mtime.tzinfo is UTC


def test_list_sessions_skips_subdirectories(fake_env: tuple[Path, Path]) -> None:
    projects, cwd = fake_env
    proj_dir = projects / encode_cwd(cwd)
    _make_session(proj_dir, "abc12345-0000-0000-0000-000000000000")
    (proj_dir / "memory").mkdir()
    (proj_dir / "memory" / "should-not-show.jsonl").write_text("{}", encoding="utf-8")
    result = list_sessions()
    assert len(result) == 1
    assert result[0].session_id == "abc12345-0000-0000-0000-000000000000"


def test_list_sessions_sorted_by_mtime_descending(fake_env: tuple[Path, Path]) -> None:
    projects, cwd = fake_env
    proj_dir = projects / encode_cwd(cwd)
    _make_session(proj_dir, "00000000-old", mtime_offset=-1000)
    _make_session(proj_dir, "11111111-mid", mtime_offset=0)
    _make_session(proj_dir, "22222222-new", mtime_offset=1000)
    ids = [s.session_id.split("-")[0] for s in list_sessions()]
    assert ids == ["22222222", "11111111", "00000000"]


def test_list_sessions_explicit_cwd_overrides_default(fake_env: tuple[Path, Path]) -> None:
    projects, _cwd = fake_env
    other_cwd = projects.parent / "other"
    other_cwd.mkdir()
    proj_dir = projects / encode_cwd(other_cwd)
    _make_session(proj_dir, "ffffffff-0000-0000-0000-000000000000")
    result = list_sessions(other_cwd)
    assert len(result) == 1
    assert result[0].session_id.startswith("ffffffff")


def test_find_latest_session_none_when_empty(fake_env: tuple[Path, Path]) -> None:
    assert find_latest_session() is None


def test_find_latest_session_returns_newest(fake_env: tuple[Path, Path]) -> None:
    projects, cwd = fake_env
    proj_dir = projects / encode_cwd(cwd)
    _make_session(proj_dir, "00000000-old", mtime_offset=-1000)
    _make_session(proj_dir, "22222222-new", mtime_offset=1000)
    result = find_latest_session()
    assert result is not None
    assert result.session_id.startswith("22222222")


def test_find_session_by_id_prefix_match(fake_env: tuple[Path, Path]) -> None:
    projects, cwd = fake_env
    proj_dir = projects / encode_cwd(cwd)
    _make_session(proj_dir, "abc12345-0000-0000-0000-000000000000")
    _make_session(proj_dir, "def67890-0000-0000-0000-000000000000")
    result = find_session_by_id("abc")
    assert result.session_id.startswith("abc12345")


def test_find_session_by_id_full_uuid_works(fake_env: tuple[Path, Path]) -> None:
    projects, cwd = fake_env
    proj_dir = projects / encode_cwd(cwd)
    full = "abc12345-0000-0000-0000-000000000000"
    _make_session(proj_dir, full)
    assert find_session_by_id(full).session_id == full


def test_find_session_by_id_ambiguous_raises(fake_env: tuple[Path, Path]) -> None:
    projects, cwd = fake_env
    proj_dir = projects / encode_cwd(cwd)
    _make_session(proj_dir, "abc11111-0000-0000-0000-000000000000")
    _make_session(proj_dir, "abc22222-0000-0000-0000-000000000000")
    with pytest.raises(AmbiguousMatchError) as exc_info:
        find_session_by_id("abc")
    assert "abc11111" in str(exc_info.value)
    assert "abc22222" in str(exc_info.value)


def test_find_session_by_id_not_found_raises(fake_env: tuple[Path, Path]) -> None:
    projects, cwd = fake_env
    proj_dir = projects / encode_cwd(cwd)
    _make_session(proj_dir, "abc12345-0000-0000-0000-000000000000")
    with pytest.raises(SessionNotFoundError) as exc_info:
        find_session_by_id("zzz")
    assert "zzz" in str(exc_info.value)


def test_find_session_by_id_not_found_when_no_project_dir(fake_env: tuple[Path, Path]) -> None:
    with pytest.raises(SessionNotFoundError):
        find_session_by_id("abc")
