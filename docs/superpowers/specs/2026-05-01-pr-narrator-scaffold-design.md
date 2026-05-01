# pr-narrator — Initial Repository Scaffold (Design)

**Date:** 2026-05-01
**Status:** Approved (specified directly by project owner)
**Branch:** `chore/initial-scaffold`

## Goal

Stand up an installable, runnable Python 3.11+ CLI package called `pr-narrator`
with all tooling, contributor guides, and templates needed to take feature work
in subsequent sessions. No feature code yet — the CLI prints only a version
stub. CI is deliberately deferred to the next session.

## Non-goals

- Feature code (transcript reading, diff parsing, `claude -p` integration)
- GitHub Actions workflows
- Real README content beyond a one-line placeholder
- Publishing to PyPI

## Architecture

Standard `src/`-layout Python package built with `hatchling` and managed
end-to-end by `uv` (sync, run, build). Single CLI entry point. Tests with
`pytest`. Lint/format with `ruff`. Type-check with `mypy`. Conventional commits
enforced via `commitizen`. Pre-commit hooks wire all of these together for
local enforcement until CI lands.

## Components

### Package — `src/pr_narrator/`
- `__init__.py` — single source of truth for `__version__`, read from
  installed package metadata via `importlib.metadata.version("pr-narrator")`.
  Fall back to `"0.0.0"` only if metadata lookup raises (defensive for
  unusual install paths). Version itself lives in `pyproject.toml`.
- `cli.py` — `main()` prints `pr-narrator v{__version__}` and returns 0.
  Implemented with `click` for forward compatibility (subcommands later) but
  kept minimal: a single `@click.command()` with no args.

### Tests — `tests/`
- `test_version.py` — asserts `__version__` is a non-empty `str` matching a
  semver regex (`^\d+\.\d+\.\d+`).
- `test_cli.py` — uses `click.testing.CliRunner` to invoke the command and
  assert exit code 0 and stdout contains `pr-narrator v` followed by the
  current `__version__`.

### Build & metadata — `pyproject.toml`
- `[build-system]` — `hatchling`
- `[project]` — name `pr-narrator`, version `0.0.1`, Python `>=3.11`,
  Apache-2.0 license, authors, README, classifiers, keywords, runtime dep
  `click>=8.1`.
- `[project.scripts]` — `pr-narrator = "pr_narrator.cli:main"`
- `[project.optional-dependencies]` `dev` — `pytest`, `pytest-cov`, `ruff`,
  `mypy`, `commitizen`, `pre-commit`.
- `[tool.ruff]` — target Python 3.11, line length 100, select common rule
  groups (E, F, I, B, UP, N, SIM), `src = ["src", "tests"]`.
- `[tool.mypy]` — strict mode, `python_version = "3.11"`, packages =
  `pr_narrator`.
- `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, addopts include
  coverage on `src/pr_narrator`.
- `[tool.coverage.run]` / `[tool.coverage.report]` — branch coverage,
  `show_missing`.
- `[tool.commitizen]` — `name = "cz_conventional_commits"`,
  `version_provider = "pep621"` so the version stays in `pyproject.toml`
  itself (no separate `_version.py`).

### Tooling files
- `.gitignore` — Python artifacts, uv venv, IDE noise.
- `.python-version` — `3.11`.
- `.pre-commit-config.yaml` — `pre-commit-hooks` (end-of-file-fixer,
  trailing-whitespace, check-yaml, check-toml), `ruff` (lint + format),
  `mypy`, and `commitizen` for `commit-msg` stage.
- `LICENSE` — Apache-2.0 full text, copyright `2026 Nagendra`.

### Repository docs
- `README.md` — single-line placeholder.
- `CONTRIBUTING.md` — branch naming, conventional commits with examples,
  PR rules (linear history, squash merge, must pass CI), local dev setup
  (`uv sync --all-extras`, `uv run pytest`, `uv run pre-commit install`).
- `CHANGELOG.md` — Keep a Changelog format with a single `[Unreleased]`
  section listing the scaffolding work.

### `.github/`
- `PULL_REQUEST_TEMPLATE.md` — short, checkbox-driven: What changed / Why /
  How tested / Linked issues / Breaking changes.
- `ISSUE_TEMPLATE/bug_report.yml` — YAML form: what happened, expected,
  repro steps, environment (python version, OS, claude-code version).
- `ISSUE_TEMPLATE/feature_request.yml` — YAML form: problem, proposed
  solution, alternatives considered.

## Data flow

There is no runtime data flow yet. The CLI's only behaviour:

```
$ pr-narrator
pr-narrator v0.0.1
$ echo $?
0
```

## Verification

Run from repo root with `uv`:

1. `uv sync --all-extras` — resolve and install package + dev deps.
2. `uv run pytest` — both tests must pass.
3. `uv run ruff check` — clean.
4. `uv run mypy src/` — clean.

If any of these fail, fix before commit phase.

## Git workflow

Logical commit groups, all conventional:
1. `chore: add Python project scaffolding` — `pyproject.toml`, `src/`,
   `tests/`, `.python-version`, `.gitignore`.
2. `chore: add license and changelog` — `LICENSE`, `CHANGELOG.md`.
3. `chore: add contributor guides and templates` — `CONTRIBUTING.md`,
   `README.md`, `.github/`.
4. `chore: add pre-commit hooks` — `.pre-commit-config.yaml`.

(The design doc itself lands in a separate prior `docs:` commit so it doesn't
mingle with scaffold groupings.)

Then push `-u origin chore/initial-scaffold` and open a non-draft PR titled
`chore: initial repository scaffold` against `main`, body filled from the new
PR template.

## Risks / open questions

- **`importlib.metadata` for unbuilt source tree.** If tests run against a
  raw checkout without `uv sync`, version lookup fails. Mitigation: tests
  are run via `uv run pytest`, which uses the installed package; the
  defensive fallback covers the edge case anyway.
- **`commitizen` pre-commit on the very first commit.** Conventional-commit
  format is enforced; we must use compliant subjects for all four commits
  (we do).
- **`mypy --strict` with `click`.** `click` ships type stubs since 8.1; no
  extra `types-*` package needed.
