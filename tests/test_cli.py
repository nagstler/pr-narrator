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


# ---------------------------------------------------------------------------
# create command tests
# ---------------------------------------------------------------------------

from pr_narrator.github import PRInfo as _PRInfo  # noqa: E402


def _stub_create_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    branch: str = "feat/x",
    commit_messages: list[str] | None = None,
    on_remote: bool = True,
    existing_pr: _PRInfo | None = None,
) -> dict[str, object]:
    """Stub all the IO surfaces the create command touches."""
    state: dict[str, object] = {
        "pushed": False,
        "created": None,
        "synth_called": False,
    }
    monkeypatch.setattr("pr_narrator.cli.get_current_branch", lambda: branch)
    monkeypatch.setattr("pr_narrator.cli.get_branch_diff", lambda base="main": "")
    monkeypatch.setattr("pr_narrator.cli.get_changed_files", lambda base="main": [])
    msgs = ["feat: x"] if commit_messages is None else commit_messages
    monkeypatch.setattr("pr_narrator.cli.get_commit_messages", lambda base="main": msgs)
    monkeypatch.setattr("pr_narrator.cli.get_remote_pr_for_branch", lambda b: existing_pr)
    monkeypatch.setattr(
        "pr_narrator.cli.is_branch_on_remote",
        lambda b, remote="origin": on_remote,
    )

    def _push(b: str, remote: str = "origin") -> None:
        state["pushed"] = True

    monkeypatch.setattr("pr_narrator.cli.push_branch", _push)

    def _create(title: str, body: str, base: str = "main", draft: bool = True) -> str:
        state["created"] = {"title": title, "body": body, "base": base, "draft": draft}
        return "https://github.com/x/y/pull/99"

    monkeypatch.setattr("pr_narrator.cli.create_pr", _create)

    def _synth(**_kw: object) -> _SynthesisResult:
        state["synth_called"] = True
        return _fake_result()

    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", _synth)
    return state


def test_create_on_main_exits_one(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_create_env(monkeypatch, branch="main")
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 1
    assert "main" in result.stderr.lower()
    assert "feature branch" in result.stderr


def test_create_with_open_pr_prints_url_and_exits_zero(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    state = _stub_create_env(
        monkeypatch,
        existing_pr=_PRInfo(number=42, state="OPEN", url="https://github.com/x/y/pull/42"),
    )
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 0, result.stderr
    assert "https://github.com/x/y/pull/42" in result.stdout
    assert state["synth_called"] is False
    assert state["created"] is None


def test_create_with_merged_pr_exits_one(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_create_env(
        monkeypatch,
        existing_pr=_PRInfo(number=42, state="MERGED", url="https://github.com/x/y/pull/42"),
    )
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 1
    assert "merged" in result.stderr.lower()


def test_create_with_closed_pr_proceeds_to_make_new_pr(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    state = _stub_create_env(
        monkeypatch,
        existing_pr=_PRInfo(number=42, state="CLOSED", url="https://github.com/x/y/pull/42"),
    )
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 0, result.stderr
    assert state["created"] is not None


def test_create_with_closed_pr_and_no_create_on_closed_exits_zero(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    state = _stub_create_env(
        monkeypatch,
        existing_pr=_PRInfo(number=42, state="CLOSED", url="https://github.com/x/y/pull/42"),
    )
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest", "--no-create-on-closed"])
    assert result.exit_code == 0, result.stderr
    assert state["created"] is None
    assert "https://github.com/x/y/pull/42" in result.stdout


def test_create_dry_run_does_not_push_or_create(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    state = _stub_create_env(monkeypatch, on_remote=False)
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest", "--dry-run"])
    assert result.exit_code == 0, result.stderr
    assert state["pushed"] is False
    assert state["created"] is None
    assert state["synth_called"] is True
    assert "## body" in result.stdout


def test_create_auto_pushes_when_branch_not_on_remote(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    state = _stub_create_env(monkeypatch, on_remote=False)
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 0, result.stderr
    assert state["pushed"] is True
    assert "Pushing branch" in result.stderr


def test_create_skips_push_when_branch_on_remote(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    state = _stub_create_env(monkeypatch, on_remote=True)
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 0, result.stderr
    assert state["pushed"] is False


def test_create_builds_title_from_frontmatter_when_complete(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    state = _stub_create_env(monkeypatch, commit_messages=["feat: add create command"])

    def _synth(**_kw: object) -> _SynthesisResult:
        r = _fake_result()
        return _SynthesisResult(
            markdown=r.markdown,
            frontmatter={
                "change_type": "feat",
                "scope": "cli",
                "risk_level": "low",
            },
            frontmatter_complete=True,
            raw_response=r.raw_response,
            prompt=r.prompt,
            model=r.model,
            cost_estimate_usd=r.cost_estimate_usd,
            truncation_notes=[],
        )

    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", _synth)
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 0, result.stderr
    assert state["created"] is not None
    assert state["created"]["title"] == "feat(cli): add create command"  # type: ignore[index]


def test_create_falls_back_to_commit_subject_when_frontmatter_incomplete(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    state = _stub_create_env(monkeypatch, commit_messages=["chore(deps): bump click to 8.1.7"])

    def _synth(**_kw: object) -> _SynthesisResult:
        r = _fake_result(complete=False)
        return _SynthesisResult(
            markdown=r.markdown,
            frontmatter=None,
            frontmatter_complete=False,
            raw_response=r.raw_response,
            prompt=r.prompt,
            model=r.model,
            cost_estimate_usd=r.cost_estimate_usd,
            truncation_notes=[],
        )

    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", _synth)
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 0, result.stderr
    assert state["created"] is not None
    assert state["created"]["title"] == "chore(deps): bump click to 8.1.7"  # type: ignore[index]


def test_create_no_draft_passes_draft_false(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    state = _stub_create_env(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest", "--no-draft"])
    assert result.exit_code == 0, result.stderr
    assert state["created"] is not None
    assert state["created"]["draft"] is False  # type: ignore[index]


def test_create_force_new_bypasses_existing_pr_check(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    state = _stub_create_env(
        monkeypatch,
        existing_pr=_PRInfo(number=42, state="OPEN", url="https://github.com/x/y/pull/42"),
    )
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest", "--force-new"])
    assert result.exit_code == 0, result.stderr
    assert state["created"] is not None


def test_create_no_session_found_exits_one(fake_cli_env: tuple[Path, Path]) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 1
    assert "No Claude Code sessions" in result.stderr


def test_create_from_no_match_exits_one(fake_cli_env: tuple[Path, Path]) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["create", "from", "deadbeef"])
    assert result.exit_code == 1
    assert "No Claude Code session" in result.stderr


def test_create_not_in_git_repo_exits_one(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)

    def _raise(*_a: object, **_kw: object) -> str:
        raise NotInGitRepoError("not a git repo")

    monkeypatch.setattr("pr_narrator.cli.get_current_branch", _raise)
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 1
    assert "not a git repo" in result.stderr


def test_create_get_remote_pr_error_exits_one(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_create_env(monkeypatch)
    from pr_narrator.errors import PRCreationError as _PRCreationError

    def _raise(_branch: str) -> _PRInfo | None:
        raise _PRCreationError("gh pr list boom")

    monkeypatch.setattr("pr_narrator.cli.get_remote_pr_for_branch", _raise)
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 1
    assert "gh pr list boom" in result.stderr


def test_create_diff_failure_exits_one(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from pr_narrator.errors import UnknownBaseRefError as _UnknownBaseRefError

    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_create_env(monkeypatch)

    def _raise(base: str = "main") -> str:
        raise _UnknownBaseRefError("bad ref")

    monkeypatch.setattr("pr_narrator.cli.get_branch_diff", _raise)
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 1
    assert "bad ref" in result.stderr


def test_create_synthesis_error_exits_one(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_create_env(monkeypatch)

    def _raise(**_kw: object) -> _SynthesisResult:
        raise _SynthesisError("synth boom")

    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", _raise)
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 1
    assert "synth boom" in result.stderr


def test_create_push_failure_exits_one(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_create_env(monkeypatch, on_remote=False)
    from pr_narrator.errors import PushFailedError as _PushFailedError

    def _raise(_b: str, remote: str = "origin") -> None:
        raise _PushFailedError("push rejected")

    monkeypatch.setattr("pr_narrator.cli.push_branch", _raise)
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 1
    assert "push rejected" in result.stderr


def test_create_pr_creation_failure_exits_one(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_create_env(monkeypatch)
    from pr_narrator.errors import PRCreationError as _PRCreationError

    def _raise(title: str, body: str, base: str = "main", draft: bool = True) -> str:
        raise _PRCreationError("gh pr create boom")

    monkeypatch.setattr("pr_narrator.cli.create_pr", _raise)
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 1
    assert "gh pr create boom" in result.stderr


def test_create_from_uses_specific_session(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd, session_id="abc12345-0000-0000-0000-000000000000")
    state = _stub_create_env(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(main, ["create", "from", "abc12345"])
    assert result.exit_code == 0, result.stderr
    assert state["created"] is not None


def test_create_no_commits_uses_placeholder_title(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    state = _stub_create_env(monkeypatch, commit_messages=[])
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest"])
    assert result.exit_code == 0, result.stderr
    assert state["created"] is not None
    assert state["created"]["title"] == "(no commits on branch)"  # type: ignore[index]


# ---------------------------------------------------------------------------
# redaction integration tests
# ---------------------------------------------------------------------------


from pr_narrator.redactor import Redaction as _Redaction  # noqa: E402


def _result_with_redactions(
    redactions: list[_Redaction] | None = None,
) -> _SynthesisResult:
    base = _fake_result()
    return _SynthesisResult(
        markdown=base.markdown,
        frontmatter=base.frontmatter,
        frontmatter_complete=base.frontmatter_complete,
        raw_response=base.raw_response,
        prompt=base.prompt,
        model=base.model,
        cost_estimate_usd=base.cost_estimate_usd,
        truncation_notes=list(base.truncation_notes),
        redactions=list(redactions) if redactions else [],
    )


def test_synthesize_paranoid_flag_propagates(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_git(monkeypatch)

    captured: dict[str, object] = {}

    def _synth(**kwargs: object) -> _SynthesisResult:
        captured.update(kwargs)
        return _fake_result()

    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", _synth)
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "latest", "--paranoid"])
    assert result.exit_code == 0, result.stderr
    assert captured.get("paranoid") is True


def test_synthesize_default_does_not_set_paranoid(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_git(monkeypatch)

    captured: dict[str, object] = {}

    def _synth(**kwargs: object) -> _SynthesisResult:
        captured.update(kwargs)
        return _fake_result()

    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", _synth)
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "latest"])
    assert result.exit_code == 0, result.stderr
    assert captured.get("paranoid") is False


def test_debug_shows_redactions_block_when_redactions_present(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_git(monkeypatch)

    fake = _result_with_redactions(
        [
            _Redaction(
                category="anthropic_api_key",
                location="user_intent_chain[2]",
                span=(10, 60),
            ),
            _Redaction(
                category="aws_access_key",
                location="diff:src/config.py:line 14",
                span=(120, 140),
            ),
        ]
    )
    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", lambda **_kw: fake)
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "latest", "--debug"])
    assert result.exit_code == 0, result.stderr
    assert "REDACTIONS (2 applied)" in result.stderr
    assert "anthropic_api_key in user_intent_chain[2]" in result.stderr
    assert "aws_access_key in diff:src/config.py:line 14" in result.stderr
    assert "@ bytes 10-60" in result.stderr


def test_debug_omits_redactions_block_when_none(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    _stub_git(monkeypatch)
    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", lambda **_kw: _fake_result())
    runner = CliRunner()
    result = runner.invoke(main, ["synthesize", "latest", "--debug"])
    assert result.exit_code == 0, result.stderr
    assert "REDACTIONS" not in result.stderr


def test_create_paranoid_flag_propagates(
    fake_cli_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, cwd = fake_cli_env
    _install_fixture_session(projects, cwd)
    state = _stub_create_env(monkeypatch)

    captured: dict[str, object] = {}

    def _synth(**kwargs: object) -> _SynthesisResult:
        captured.update(kwargs)
        state["synth_called"] = True
        return _fake_result()

    monkeypatch.setattr("pr_narrator.cli.synthesize_pr_description", _synth)
    runner = CliRunner()
    result = runner.invoke(main, ["create", "latest", "--paranoid"])
    assert result.exit_code == 0, result.stderr
    assert captured.get("paranoid") is True


# ---------------------------------------------------------------------------
# _pick_title_source unit tests (skip noisy commits)
# ---------------------------------------------------------------------------

from pr_narrator.cli import _pick_title_source  # noqa: E402


def test_pick_title_source_returns_newest_when_no_skip_match() -> None:
    # commit_messages comes from git log: newest first, oldest last
    msgs = [
        "feat: add new feature",
        "chore: bump deps",
    ]
    assert _pick_title_source(msgs) == "feat: add new feature"


def test_pick_title_source_skips_docs_commit_for_feature_commit() -> None:
    msgs = [
        "docs: fix typo in README",
        "feat(cli): add --paranoid flag",
    ]
    assert _pick_title_source(msgs) == "feat(cli): add --paranoid flag"


def test_pick_title_source_skips_multiple_consecutive_style_commits() -> None:
    msgs = [
        "style: ruff format",
        "style(cli): reflow long line",
        "style: trailing whitespace",
        "feat(redactor): add JWT pattern",
    ]
    assert _pick_title_source(msgs) == "feat(redactor): add JWT pattern"


def test_pick_title_source_skips_fixup_and_squash_markers() -> None:
    msgs = [
        "fixup! feat: add x",
        "squash! feat: add x",
        "feat(parser): handle empty diff hunks",
    ]
    assert _pick_title_source(msgs) == "feat(parser): handle empty diff hunks"


def test_pick_title_source_skips_chore_format_commits() -> None:
    msgs = [
        "chore: format with ruff",
        "chore: apply formatting",  # contains "format"
        "fix(synthesizer): retry on transient claude error",
    ]
    assert _pick_title_source(msgs) == "fix(synthesizer): retry on transient claude error"


def test_pick_title_source_does_not_skip_non_format_chore() -> None:
    msgs = [
        "chore: bump click to 8.2",
    ]
    assert _pick_title_source(msgs) == "chore: bump click to 8.2"


def test_pick_title_source_skips_wip_commits() -> None:
    msgs = [
        "wip: still working on it",
        "wip(cli): partial flag",
        "feat(cli): finish flag",
    ]
    assert _pick_title_source(msgs) == "feat(cli): finish flag"


def test_pick_title_source_skip_match_is_case_insensitive_on_prefix() -> None:
    msgs = [
        "Docs: capitalised type",
        "STYLE: shouty",
        "feat(api): the real change",
    ]
    assert _pick_title_source(msgs) == "feat(api): the real change"


def test_pick_title_source_falls_back_to_newest_when_all_match_skip_patterns() -> None:
    msgs = [
        "docs: tweak",
        "style: reflow",
        "chore: format",
    ]
    # All match skip patterns; fall back to the newest commit subject.
    assert _pick_title_source(msgs) == "docs: tweak"


def test_pick_title_source_empty_list_returns_no_commits_marker() -> None:
    assert _pick_title_source([]) == "(no commits on branch)"


def test_build_pr_title_uses_newest_commit_with_complete_frontmatter() -> None:
    """Regression: the picker must walk newest-first, not oldest-first."""
    from pr_narrator.cli import _build_pr_title
    from pr_narrator.synthesizer import SynthesisResult

    result = SynthesisResult(
        markdown="body",
        frontmatter={"change_type": "feat", "scope": "cli", "risk_level": "low"},
        frontmatter_complete=True,
        raw_response="{}",
        prompt="p",
        model="claude-opus",
        cost_estimate_usd=None,
        truncation_notes=[],
    )
    msgs = ["feat: newest change", "feat: oldest change"]  # git log order
    assert _build_pr_title(result, msgs) == "feat(cli): newest change"


# ---------------------------------------------------------------------------
# change_type-aware picker tests
# ---------------------------------------------------------------------------


def test_pick_title_source_with_change_type_docs_does_not_skip_docs_commits() -> None:
    """Docs PRs should source their title from a docs commit, not a stray fix."""
    msgs = [
        "docs(readme): correct dry-run example",
        "docs: rewrite README",
        "fix(cli): unrelated small fix",
    ]
    assert _pick_title_source(msgs, change_type="docs") == "docs(readme): correct dry-run example"


def test_pick_title_source_with_change_type_docs_still_skips_style_and_fixup() -> None:
    msgs = [
        "fixup! something",
        "style: ruff format",
        "docs(readme): real change",
    ]
    assert _pick_title_source(msgs, change_type="docs") == "docs(readme): real change"


def test_pick_title_source_with_change_type_style_does_not_skip_style_commits() -> None:
    msgs = [
        "style(ui): align headers",
        "docs: update faq",
    ]
    assert _pick_title_source(msgs, change_type="style") == "style(ui): align headers"


def test_pick_title_source_with_change_type_wip_does_not_skip_wip_commits() -> None:
    msgs = [
        "wip(api): partial endpoint",
        "docs: notes",
    ]
    assert _pick_title_source(msgs, change_type="wip") == "wip(api): partial endpoint"


def test_pick_title_source_with_change_type_feat_behaves_like_no_hint() -> None:
    msgs = [
        "docs: tweak",
        "feat(cli): add flag",
    ]
    # change_type='feat' isn't a skip category, so behavior is identical to None.
    assert _pick_title_source(msgs, change_type="feat") == "feat(cli): add flag"
    assert _pick_title_source(msgs) == "feat(cli): add flag"


def test_pick_title_source_with_change_type_none_is_default_behavior() -> None:
    msgs = ["docs: x", "feat: y"]
    assert _pick_title_source(msgs, change_type=None) == "feat: y"


def test_build_pr_title_threads_change_type_into_picker() -> None:
    """Regression: docs-heavy PRs must not borrow titles from a stray fix commit."""
    from pr_narrator.cli import _build_pr_title
    from pr_narrator.synthesizer import SynthesisResult

    result = SynthesisResult(
        markdown="body",
        frontmatter={"change_type": "docs", "scope": "readme", "risk_level": "low"},
        frontmatter_complete=True,
        raw_response="{}",
        prompt="p",
        model="claude-opus",
        cost_estimate_usd=None,
        truncation_notes=[],
    )
    msgs = [
        "docs(readme): rewrite README for v0.1",
        "docs: update CHANGELOG",
        "fix(cli): unrelated",
    ]
    # Without change_type-awareness this would be 'docs(readme): unrelated'.
    assert _build_pr_title(result, msgs) == "docs(readme): rewrite README for v0.1"
