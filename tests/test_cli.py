"""Tests for the pr-narrator CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from pr_narrator import __version__
from pr_narrator.cli import main


def test_version_flag_prints_version() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"pr-narrator v{__version__}"


FIXTURE_SRC = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


@pytest.fixture
def fake_cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Mirror the discovery fixture so the CLI sees a controlled tmp tree."""
    projects = tmp_path / "projects"
    fake_cwd = tmp_path / "myproj"
    fake_cwd.mkdir()
    monkeypatch.chdir(fake_cwd)
    monkeypatch.setattr("pr_narrator.discovery.get_projects_dir", lambda: projects)
    return projects, fake_cwd


def _install_fixture_session(
    projects: Path,
    cwd: Path,
    session_id: str = "deadbeef-1111-2222-3333-444455556666",
) -> Path:
    from pr_narrator.discovery import encode_cwd

    proj_dir = projects / encode_cwd(cwd)
    proj_dir.mkdir(parents=True, exist_ok=True)
    target = proj_dir / f"{session_id}.jsonl"
    target.write_bytes(FIXTURE_SRC.read_bytes())
    return target


def test_inspect_latest_no_sessions_exits_one(fake_cli_env: tuple[Path, Path]) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["inspect", "latest"])
    assert result.exit_code == 1
    assert "No Claude Code sessions" in result.stderr


def test_inspect_latest_prints_summary(fake_cli_env: tuple[Path, Path]) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    runner = CliRunner()
    result = runner.invoke(main, ["inspect", "latest"])
    assert result.exit_code == 0, result.stderr
    out = result.stdout
    assert "SESSION: deadbeef" in out
    assert "USER MESSAGES (3)" in out
    assert "ASSISTANT TURNS: 6" in out
    assert "Read: 1" in out
    assert "Edit: 2" in out
    assert "Bash: 1" in out
    assert "META EVENTS:" in out
    assert "TOTAL EVENTS:" in out
    assert "[00:00] fix the bug in foo.py" in out
    assert "[01:00] no, use Redis instead" in out
    assert "…" in out


def test_inspect_latest_handles_zero_tool_calls(
    fake_cli_env: tuple[Path, Path],
) -> None:
    projects, cwd = fake_cli_env
    from pr_narrator.discovery import encode_cwd

    proj_dir = projects / encode_cwd(cwd)
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "feedface-0000-0000-0000-000000000000.jsonl").write_text(
        '{"type":"user","uuid":"u","timestamp":"2026-05-01T10:00:00Z",'
        '"message":{"role":"user","content":"hi"}}\n',
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(main, ["inspect", "latest"])
    assert result.exit_code == 0, result.stderr
    assert "TOOL CALLS: 0" in result.stdout
    assert "META EVENTS: 0" in result.stdout


def test_inspect_from_full_uuid(fake_cli_env: tuple[Path, Path]) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd, session_id="abc12345-0000-0000-0000-000000000000")
    runner = CliRunner()
    result = runner.invoke(main, ["inspect", "from", "abc12345-0000-0000-0000-000000000000"])
    assert result.exit_code == 0, result.stderr
    assert "SESSION: abc12345" in result.stdout


def test_inspect_from_prefix(fake_cli_env: tuple[Path, Path]) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd, session_id="abc12345-0000-0000-0000-000000000000")
    runner = CliRunner()
    result = runner.invoke(main, ["inspect", "from", "abc12"])
    assert result.exit_code == 0, result.stderr


def test_inspect_from_ambiguous_exits_one(fake_cli_env: tuple[Path, Path]) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd, session_id="abc11111-0000-0000-0000-000000000000")
    _install_fixture_session(projects, cwd, session_id="abc22222-0000-0000-0000-000000000000")
    runner = CliRunner()
    result = runner.invoke(main, ["inspect", "from", "abc"])
    assert result.exit_code == 1
    assert "matches 2 sessions" in result.stderr


def test_inspect_from_not_found_exits_one(fake_cli_env: tuple[Path, Path]) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd, session_id="abc12345-0000-0000-0000-000000000000")
    runner = CliRunner()
    result = runner.invoke(main, ["inspect", "from", "zzzz"])
    assert result.exit_code == 1
    assert "No Claude Code session matching" in result.stderr


def test_inspect_latest_breakdown_shows_plus_n_other(
    fake_cli_env: tuple[Path, Path],
) -> None:
    """A session with >5 distinct tools should render '+N other'."""
    projects, cwd = fake_cli_env
    from pr_narrator.discovery import encode_cwd

    proj_dir = projects / encode_cwd(cwd)
    proj_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        '{"type":"user","uuid":"u-0001","timestamp":"2026-05-01T10:00:00Z",'
        '"message":{"role":"user","content":"hi"}}'
    ]
    for i, name in enumerate(["A", "B", "C", "D", "E", "F", "G"]):
        lines.append(
            f'{{"type":"assistant","uuid":"a-{i:04d}","timestamp":"2026-05-01T10:00:0{i}Z",'
            f'"message":{{"role":"assistant","content":[{{"type":"tool_use",'
            f'"id":"t{i}","name":"{name}","input":{{}}}}]}}}}'
        )
    (proj_dir / "abcd0001-0000-0000-0000-000000000000.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    runner = CliRunner()
    result = runner.invoke(main, ["inspect", "latest"])
    assert result.exit_code == 0, result.stderr
    assert "+2 other" in result.stdout


def test_format_size_bytes_kb_mb() -> None:
    from pr_narrator.cli import _format_size

    assert _format_size(500) == "500B"
    assert _format_size(2048) == "2KB"
    assert _format_size(2 * 1024 * 1024) == "2.0MB"
