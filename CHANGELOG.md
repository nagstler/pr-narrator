# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
