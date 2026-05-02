# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `pr-narrator create [latest|from <ID>]` command — synthesizes a
  PR description and posts it as a draft GitHub PR via `gh`. Flags:
  `--base`, `--model`, `--no-draft`, `--no-frontmatter`, `--strict`,
  `--dry-run`, `--no-create-on-closed`, `--force-new`. Title is
  built from synthesis frontmatter (`{change_type}({scope}): {most
  recent commit subject, conventional-prefix stripped}`), with the
  most-recent commit subject verbatim as a fallback when
  frontmatter is incomplete. Stdout carries only the PR URL on
  success so `pr-narrator create latest | xargs open` works.
- Auto-push to `origin` when the branch isn't yet on remote, with
  a clear stderr "Pushing branch X to origin..." message.
- Existing-PR detection: skip creation if an OPEN PR exists for
  the branch (prints its URL), refuse if a MERGED PR exists, and
  default to creating a new PR for CLOSED ones (overridable with
  `--no-create-on-closed`). `--force-new` bypasses the check.
- `pr_narrator.github` module wrapping `gh pr list`, `gh pr create`,
  `git push`, and `git ls-remote` via subprocess. New errors:
  `GitHubCliNotFoundError`, `PushFailedError`, `PRCreationError`.
- Transcript compressor (`pr_narrator.compressor`): deterministic,
  rule-based compression of parsed session events into a
  `CompressedTranscript` (timeline of user / decision / tool_burst /
  tool_call / error / compaction entries plus tool-call summary,
  user-intent chain, and duration).
- Git diff capture utilities (`pr_narrator.diff`): `get_branch_diff`
  (three-dot), `get_changed_files`, `get_commit_messages` (two-dot),
  `get_current_branch`. Typed errors `NotInGitRepoError` and
  `UnknownBaseRefError`.
- LLM synthesis layer (`pr_narrator.synthesizer`): renders a
  compressed transcript + diff into a prompt, invokes
  `claude -p --output-format json --no-session-persistence --tools ""`
  via subprocess, parses the response into a `SynthesisResult`
  (markdown, frontmatter, cost estimate, prompt provenance,
  truncation notes, timestamp). Three-tier frontmatter validation
  with normalization and an optional `--strict` mode. Auth is
  delegated entirely to whatever Claude Code is configured with —
  pr-narrator adds no env-var requirements. New errors:
  `ClaudeBinaryNotFoundError`, `SynthesisError`.
- `pr-narrator synthesize latest` and `pr-narrator synthesize from
  <id>` CLI commands with `--base`, `--model`, `--no-frontmatter`,
  `--debug`, `--strict` options. `--debug` writes prompt and raw
  response (with byte counts) to stderr so stdout stays clean for
  piping into `gh pr create -F -`.
- Dual-audience output: GFM markdown body for human reviewers plus
  hidden YAML-style frontmatter inside an HTML comment for
  automated review bots (CodeRabbit, Greptile).
- Session transcript discovery (`list_sessions`, `find_latest_session`,
  `find_session_by_id`) under `pr_narrator.discovery`, with
  `SessionMeta`, `SessionNotFoundError`, and `AmbiguousMatchError`.
- Streaming JSONL session parser (`parse_session`, `load_session`)
  yielding typed `UserMessage`, `AssistantTurn`, `ToolCall`,
  `ToolResult`, and `MetaEvent` events; tolerates malformed lines and
  unknown event types.
- `pr-narrator inspect latest` and `pr-narrator inspect from <id>`
  CLI commands that print a structured per-session summary (header
  with size/event-count/mtime, user-message timeline with relative
  mm:ss timestamps, top-5 tool-call breakdown, meta-event counts).
- Initial Python project scaffolding: `pyproject.toml` (hatchling build backend),
  `src/pr_narrator/` package with version export and `pr-narrator` CLI entry
  point printing a version stub.
- Test suite skeleton (`pytest`, `pytest-cov`) covering the version export and
  the CLI entry point.
- Tooling configuration: `ruff` (lint + format), `mypy --strict`, `commitizen`
  using `cz_conventional_commits` with the version stored in `pyproject.toml`.
- Pre-commit hooks: ruff (lint + format), mypy, file hygiene
  (end-of-file-fixer, trailing-whitespace, check-yaml, check-toml), and
  commitizen for commit-message validation.
- Apache-2.0 `LICENSE`.
- Contributor documentation: `CONTRIBUTING.md` (branch naming, conventional
  commits, PR rules, local dev with `uv`), one-line placeholder `README.md`.
- GitHub templates: pull request template and YAML issue form templates for
  bug reports and feature requests.

[Unreleased]: https://github.com/nagstler/pr-narrator/compare/HEAD...HEAD
