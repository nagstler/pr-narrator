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


# ---------------------------------------------------------------------------
# synthesize command tests
# ---------------------------------------------------------------------------

import json as _json  # noqa: E402
from decimal import Decimal as _Decimal  # noqa: E402

from pr_narrator.errors import NotInGitRepoError  # noqa: E402
from pr_narrator.errors import SynthesisError as _SynthesisError  # noqa: E402
from pr_narrator.synthesizer import SynthesisResult as _SynthesisResult  # noqa: E402


def _fake_result(markdown_body: str = "## body\n", complete: bool = True) -> _SynthesisResult:
    fm = "<!-- pr-narrator-meta\nchange_type: feat\nrisk_level: low\n-->\n\n"
    full = fm + markdown_body
    return _SynthesisResult(
        markdown=full,
        frontmatter={"change_type": "feat", "risk_level": "low"} if complete else None,
        frontmatter_complete=complete,
        raw_response=_json.dumps({"result": full, "cost_usd": 0.01}),
        prompt="SYS\n---\nUSR",
        model="sonnet",
        cost_estimate_usd=_Decimal("0.01"),
        truncation_notes=["Diff tail truncated: 999 bytes omitted"],
    )


def _stub_git(stack: pytest.MonkeyPatch) -> None:
    stack.setattr("pr_narrator.cli.get_current_branch", lambda: "feat/x")
    stack.setattr("pr_narrator.cli.get_branch_diff", lambda base="main": "")
    stack.setattr("pr_narrator.cli.get_changed_files", lambda base="main": [])
    stack.setattr("pr_narrator.cli.get_commit_messages", lambda base="main": [])


def test_synthesize_latest_no_session_exits_one(fake_cli_env: tuple[Path, Path]) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "latest"])
    assert result.exit_code == 1
    assert "No Claude Code sessions" in result.stderr


def test_synthesize_from_ambiguous_exits_one(fake_cli_env: tuple[Path, Path]) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd, session_id="abc11111-0000-0000-0000-000000000000")
    _install_fixture_session(projects, cwd, session_id="abc22222-0000-0000-0000-000000000000")
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "from", "abc"])
    assert result.exit_code == 1
    assert "matches 2 sessions" in result.stderr


def test_synthesize_no_frontmatter_strips_comment(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_git(monkeypatch)
    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", lambda **_kw: _fake_result())
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "latest", "--no-frontmatter"])
    assert result.exit_code == 0, result.stderr
    assert "<!-- pr-narrator-meta" not in result.stdout
    assert "## body" in result.stdout


def test_synthesize_default_keeps_frontmatter(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_git(monkeypatch)
    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", lambda **_kw: _fake_result())
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "latest"])
    assert result.exit_code == 0, result.stderr
    assert "<!-- pr-narrator-meta" in result.stdout


def test_synthesize_debug_writes_to_stderr_only(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_git(monkeypatch)
    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", lambda **_kw: _fake_result())
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "latest", "--debug"])
    assert result.exit_code == 0, result.stderr
    assert "=== PROMPT" in result.stderr
    assert "=== PROMPT" not in result.stdout
    assert "## body" in result.stdout
    assert "Diff tail truncated" in result.stderr  # truncation note shown


def test_synthesize_debug_handles_unparseable_raw_response(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_git(monkeypatch)

    def _result_with_bad_json(**_kw: object) -> _SynthesisResult:
        r = _fake_result()
        return _SynthesisResult(
            markdown=r.markdown,
            frontmatter=r.frontmatter,
            frontmatter_complete=r.frontmatter_complete,
            raw_response="not valid json {",
            prompt=r.prompt,
            model=r.model,
            cost_estimate_usd=r.cost_estimate_usd,
            truncation_notes=[],
        )

    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", _result_with_bad_json)
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "latest", "--debug"])
    assert result.exit_code == 0, result.stderr
    assert "not valid json {" in result.stderr
    assert "(none)" in result.stderr  # empty truncation_notes path


def test_synthesize_debug_with_no_cost(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_git(monkeypatch)

    def _no_cost(**_kw: object) -> _SynthesisResult:
        r = _fake_result()
        return _SynthesisResult(
            markdown=r.markdown,
            frontmatter=r.frontmatter,
            frontmatter_complete=r.frontmatter_complete,
            raw_response=r.raw_response,
            prompt=r.prompt,
            model=r.model,
            cost_estimate_usd=None,
            truncation_notes=r.truncation_notes,
        )

    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", _no_cost)
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "latest", "--debug"])
    assert result.exit_code == 0
    assert "(unknown)" in result.stderr


def test_synthesize_strict_propagates(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_git(monkeypatch)
    captured: dict[str, object] = {}

    def _capture(**kwargs: object) -> _SynthesisResult:
        captured.update(kwargs)
        return _fake_result()

    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", _capture)
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "latest", "--strict"])
    assert result.exit_code == 0, result.stderr
    assert captured["strict"] is True


def test_synthesize_base_propagates(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    captured_base: list[str] = []

    def _diff_capture(base: str = "main") -> str:
        captured_base.append(base)
        return ""

    monkeypatch.setattr("pr_narrator.cli.get_current_branch", lambda: "feat/x")
    monkeypatch.setattr("pr_narrator.cli.get_branch_diff", _diff_capture)
    monkeypatch.setattr("pr_narrator.cli.get_changed_files", lambda base="main": [])
    monkeypatch.setattr("pr_narrator.cli.get_commit_messages", lambda base="main": [])
    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", lambda **_kw: _fake_result())
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "latest", "--base", "develop"])
    assert result.exit_code == 0, result.stderr
    assert "develop" in captured_base


def test_synthesize_synthesis_error_exits_one_no_partial_stdout(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_git(monkeypatch)

    def _raise(**_kw: object) -> _SynthesisResult:
        raise _SynthesisError("boom")

    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", _raise)
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "latest"])
    assert result.exit_code == 1
    assert "boom" in result.stderr
    assert result.stdout.strip() == ""


def test_synthesize_not_in_git_repo_exits_one(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)

    def _raise(*_a: object, **_kw: object) -> str:
        raise NotInGitRepoError("not a git repo")

    monkeypatch.setattr("pr_narrator.cli.get_current_branch", _raise)
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "latest"])
    assert result.exit_code == 1
    assert "not a git repo" in result.stderr


def test_strip_frontmatter_no_comment_returns_unchanged() -> None:
    from pr_narrator.cli import _strip_frontmatter

    text = "## body\nno frontmatter here\n"
    assert _strip_frontmatter(text) == text


def test_strip_frontmatter_unclosed_comment_returns_unchanged() -> None:
    from pr_narrator.cli import _strip_frontmatter

    text = "<!-- pr-narrator-meta\nchange_type: feat\n## body\n"  # no -->
    assert _strip_frontmatter(text) == text


def test_synthesize_from_uses_specific_session(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd, session_id="abc12345-0000-0000-0000-000000000000")
    _stub_git(monkeypatch)
    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", lambda **_kw: _fake_result())
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "from", "abc12345"])
    assert result.exit_code == 0, result.stderr
    assert "## body" in result.stdout
