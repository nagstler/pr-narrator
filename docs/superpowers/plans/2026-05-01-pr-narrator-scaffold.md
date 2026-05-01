# pr-narrator Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up an installable, runnable Python 3.11+ CLI package (`pr-narrator`) with full tooling, contributor docs, and templates — no feature code yet. The CLI prints only a version stub.

**Architecture:** `src/`-layout package, `hatchling` build backend, managed end-to-end with `uv`. Single Click-based CLI entry point. `pytest` for tests, `ruff` + `mypy --strict` for static checks, `commitizen` for conventional commits, `pre-commit` for local enforcement.

**Tech Stack:** Python 3.11+, hatchling, uv, click, pytest, pytest-cov, ruff, mypy, commitizen, pre-commit.

---

## File Structure

| Path | Purpose |
|---|---|
| `pyproject.toml` | Build config, deps, tool config (ruff, mypy, pytest, coverage, commitizen) |
| `.python-version` | Pins Python 3.11 for `uv` |
| `.gitignore` | Python/uv/IDE artifacts |
| `src/pr_narrator/__init__.py` | Exports `__version__` from package metadata |
| `src/pr_narrator/cli.py` | Click `main()` printing version stub |
| `tests/__init__.py` | Marks tests as a package (empty) |
| `tests/test_version.py` | Asserts `__version__` non-empty + semver-shaped |
| `tests/test_cli.py` | `CliRunner` test of CLI output and exit code |
| `LICENSE` | Apache-2.0 full text |
| `CHANGELOG.md` | Keep a Changelog with `[Unreleased]` |
| `CONTRIBUTING.md` | Branch naming, conventional commits, PR rules, local dev |
| `README.md` | One-line placeholder |
| `.pre-commit-config.yaml` | Hooks: ruff, mypy, file hygiene, commitizen |
| `.github/PULL_REQUEST_TEMPLATE.md` | Short checkbox PR template |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | YAML form: bug |
| `.github/ISSUE_TEMPLATE/feature_request.yml` | YAML form: feature |

---

## Task 1: Create the Python package skeleton (TDD: version + CLI)

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.gitignore`
- Create: `src/pr_narrator/__init__.py`
- Create: `src/pr_narrator/cli.py`
- Create: `tests/__init__.py`
- Create: `tests/test_version.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1.1: Create `.python-version`**

Write file content (single line, no trailing newline issues — pre-commit `end-of-file-fixer` will normalise later):

```
3.11
```

- [ ] **Step 1.2: Create `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python

# Distribution / packaging
build/
dist/
*.egg-info/
*.egg

# Virtual envs
.venv/
venv/

# Tooling caches
.ruff_cache/
.mypy_cache/
.pytest_cache/
.coverage
.coverage.*
htmlcov/
coverage.xml

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
```

- [ ] **Step 1.3: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pr-narrator"
version = "0.0.1"
description = "Turn long Claude Code sessions into reviewer-ready pull request descriptions."
readme = "README.md"
requires-python = ">=3.11"
license = { text = "Apache-2.0" }
authors = [{ name = "Nagendra Dhanakeerthi", email = "nagendra.dhanakeerthi@gmail.com" }]
keywords = ["claude", "claude-code", "pull-request", "cli", "code-review"]
classifiers = [
  "Development Status :: 2 - Pre-Alpha",
  "Environment :: Console",
  "Intended Audience :: Developers",
  "License :: OSI Approved :: Apache Software License",
  "Operating System :: OS Independent",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Topic :: Software Development",
  "Topic :: Software Development :: Version Control :: Git",
]
dependencies = [
  "click>=8.1",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-cov>=5.0",
  "ruff>=0.6",
  "mypy>=1.10",
  "commitizen>=3.29",
  "pre-commit>=3.7",
]

[project.scripts]
pr-narrator = "pr_narrator.cli:main"

[project.urls]
Homepage = "https://github.com/nagstler/pr-narrator"
Repository = "https://github.com/nagstler/pr-narrator"
Issues = "https://github.com/nagstler/pr-narrator/issues"

[tool.hatch.build.targets.wheel]
packages = ["src/pr_narrator"]

[tool.ruff]
target-version = "py311"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "SIM"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.11"
strict = true
files = ["src/pr_narrator"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers --cov=pr_narrator --cov-report=term-missing"

[tool.coverage.run]
branch = true
source = ["pr_narrator"]

[tool.coverage.report]
show_missing = true
skip_covered = false

[tool.commitizen]
name = "cz_conventional_commits"
version_provider = "pep621"
tag_format = "v$version"
update_changelog_on_bump = true
```

- [ ] **Step 1.4: Create `src/pr_narrator/__init__.py`**

```python
"""pr-narrator: turn Claude Code sessions into reviewer-ready PR descriptions."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("pr-narrator")
except PackageNotFoundError:  # pragma: no cover - only hit in unbuilt source trees
    __version__ = "0.0.0"

__all__ = ["__version__"]
```

- [ ] **Step 1.5: Create `tests/__init__.py`** (empty file)

- [ ] **Step 1.6: Write failing version test — `tests/test_version.py`**

```python
"""Tests for the package version export."""

import re

from pr_narrator import __version__


def test_version_is_non_empty_string() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_version_matches_semver_shape() -> None:
    assert re.match(r"^\d+\.\d+\.\d+", __version__)
```

- [ ] **Step 1.7: Create `src/pr_narrator/cli.py`**

```python
"""Command-line entry point for pr-narrator."""

from __future__ import annotations

import click

from pr_narrator import __version__


@click.command()
def main() -> None:
    """Print the pr-narrator version and exit."""
    click.echo(f"pr-narrator v{__version__}")
```

- [ ] **Step 1.8: Write failing CLI test — `tests/test_cli.py`**

```python
"""Tests for the pr-narrator CLI entry point."""

from click.testing import CliRunner

from pr_narrator import __version__
from pr_narrator.cli import main


def test_cli_prints_version_and_exits_zero() -> None:
    runner = CliRunner()
    result = runner.invoke(main)
    assert result.exit_code == 0
    assert result.output.strip() == f"pr-narrator v{__version__}"
```

- [ ] **Step 1.9: Sync the environment**

Run:
```bash
uv sync --all-extras
```
Expected: resolves and installs `pr-narrator` plus all dev deps. No errors.

- [ ] **Step 1.10: Run the full test suite**

Run:
```bash
uv run pytest
```
Expected: 2 tests pass. Coverage report prints. Exit 0.

- [ ] **Step 1.11: Lint and type-check**

Run:
```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
Expected: all three exit 0. If `ruff format --check` fails, run `uv run ruff format .` and re-verify.

- [ ] **Step 1.12: Smoke-test the installed CLI**

Run:
```bash
uv run pr-narrator
```
Expected output: `pr-narrator v0.0.1`. Exit 0.

---

## Task 2: Add LICENSE and CHANGELOG

**Files:**
- Create: `LICENSE`
- Create: `CHANGELOG.md`

- [ ] **Step 2.1: Create `LICENSE`** with the full Apache-2.0 text and `Copyright 2026 Nagendra` in the standard `APPENDIX` boilerplate footer. Use the canonical Apache 2.0 text exactly as published at apache.org.

- [ ] **Step 2.2: Create `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
```

---

## Task 3: Add contributor guides and GitHub templates

**Files:**
- Create: `README.md`
- Create: `CONTRIBUTING.md`
- Create: `.github/PULL_REQUEST_TEMPLATE.md`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`

- [ ] **Step 3.1: Create `README.md`**

```markdown
# pr-narrator

Turn long Claude Code sessions into reviewer-ready pull request descriptions. (Under construction.)
```

- [ ] **Step 3.2: Create `CONTRIBUTING.md`**

```markdown
# Contributing to pr-narrator

Thanks for your interest in pr-narrator! This guide covers branch hygiene,
commit conventions, the PR process, and local development setup.

## Branch naming

Branch names use a type prefix followed by a short kebab-case description:

- `feat/<slug>` — new functionality
- `fix/<slug>` — bug fixes
- `chore/<slug>` — tooling, dependencies, repo plumbing
- `docs/<slug>` — documentation only
- `refactor/<slug>` — internal restructuring without behavior change
- `test/<slug>` — test-only changes
- `ci/<slug>` — CI/CD configuration

Examples: `feat/transcript-reader`, `fix/diff-empty-lines`,
`chore/initial-scaffold`.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/) enforced
locally by [commitizen](https://commitizen-tools.github.io/commitizen/). The
allowed types match the branch prefixes above (`feat`, `fix`, `chore`,
`docs`, `refactor`, `test`, `ci`, plus `perf`, `style`, `build`, `revert`).

```
feat(cli): add --json output flag
fix(parser): handle empty diff hunks
chore: bump click to 8.2
docs(readme): add quickstart
```

Breaking changes use a trailing `BREAKING CHANGE:` footer or `!` after the
type, e.g. `feat!: drop Python 3.10 support`.

## Pull requests

- Branch off `main`. PRs must target `main`.
- `main` enforces **linear history** and **squash merge only**. Rebase your
  branch on `main` before opening the PR if it has fallen behind.
- All checks (CI, when configured) must pass before merge.
- Fill out the PR template — keep the body short and check the boxes that
  apply.

## Local development

This project uses [uv](https://docs.astral.sh/uv/) for everything: install,
run, test, build. You should not need `pip` or `python -m venv`.

```bash
# Install Python (uv reads .python-version) and sync deps including dev
uv sync --all-extras

# Install pre-commit hooks (runs ruff, mypy, file hygiene, commitizen)
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

# Run the test suite
uv run pytest

# Lint, format, type-check
uv run ruff check .
uv run ruff format .
uv run mypy src/

# Run the CLI
uv run pr-narrator
```
```

- [ ] **Step 3.3: Create `.github/PULL_REQUEST_TEMPLATE.md`**

```markdown
## What changed
<!-- One or two sentences. -->

## Why
<!-- The motivation, linked issue, or context. -->

## How tested
- [ ] `uv run pytest` passes
- [ ] `uv run ruff check .` passes
- [ ] `uv run mypy src/` passes
- [ ] Manually exercised the change (describe below if applicable)

## Linked issues
<!-- Closes #123, refs #456. -->

## Breaking changes
- [ ] This PR introduces a breaking change (describe migration below)
```

- [ ] **Step 3.4: Create `.github/ISSUE_TEMPLATE/bug_report.yml`**

```yaml
name: Bug report
description: Report a problem with pr-narrator
title: "bug: <short description>"
labels: ["bug"]
body:
  - type: textarea
    id: what-happened
    attributes:
      label: What happened?
      description: A clear description of the unexpected behavior.
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: What did you expect to happen?
    validations:
      required: true
  - type: textarea
    id: repro
    attributes:
      label: Steps to reproduce
      description: Minimal commands or input that trigger the bug.
      placeholder: |
        1. Run `pr-narrator ...`
        2. ...
        3. See error
    validations:
      required: true
  - type: input
    id: python-version
    attributes:
      label: Python version
      placeholder: "3.11.9"
    validations:
      required: true
  - type: input
    id: os
    attributes:
      label: Operating system
      placeholder: "macOS 14.4 / Ubuntu 24.04 / Windows 11"
    validations:
      required: true
  - type: input
    id: claude-code-version
    attributes:
      label: claude-code version
      description: Output of `claude --version`, if relevant.
      placeholder: "1.0.0"
    validations:
      required: false
  - type: textarea
    id: logs
    attributes:
      label: Relevant logs or output
      render: shell
    validations:
      required: false
```

- [ ] **Step 3.5: Create `.github/ISSUE_TEMPLATE/feature_request.yml`**

```yaml
name: Feature request
description: Suggest a new capability or improvement
title: "feat: <short description>"
labels: ["enhancement"]
body:
  - type: textarea
    id: problem
    attributes:
      label: Problem
      description: What problem are you trying to solve? Who is affected?
    validations:
      required: true
  - type: textarea
    id: proposal
    attributes:
      label: Proposed solution
      description: Describe the change you would like to see.
    validations:
      required: true
  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives considered
      description: Other approaches you weighed and why you set them aside.
    validations:
      required: false
  - type: textarea
    id: context
    attributes:
      label: Additional context
      description: Links, screenshots, related issues.
    validations:
      required: false
```

---

## Task 4: Add pre-commit configuration

**Files:**
- Create: `.pre-commit-config.yaml`

- [ ] **Step 4.1: Create `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-yaml
      - id: check-toml
      - id: check-merge-conflict
      - id: check-added-large-files

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.2
    hooks:
      - id: mypy
        args: ["--config-file=pyproject.toml"]
        additional_dependencies: ["click>=8.1"]
        files: ^src/

  - repo: https://github.com/commitizen-tools/commitizen
    rev: v3.29.1
    hooks:
      - id: commitizen
        stages: [commit-msg]
```

- [ ] **Step 4.2: Verify the config parses**

Run:
```bash
uv run pre-commit validate-config
```
Expected: exit 0 (no output, or success message).

---

## Task 5: Final end-to-end verification

- [ ] **Step 5.1: Re-run the full verification matrix**

Run sequentially:
```bash
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run pre-commit validate-config
uv run pr-narrator
```
Expected: every command exits 0. `pr-narrator` prints `pr-narrator v0.0.1`.

If any fails, fix before commit phase. Common fixes:
- Ruff format complaints → `uv run ruff format .`
- Mypy strict complaints on click → confirm `click>=8.1` is installed (it ships stubs).

---

## Task 6: Commit in logical groups

Each commit uses Conventional Commits format. Use `git add <paths>` (not `-A`/`-.`) to keep groupings tight.

- [ ] **Step 6.1: Commit the scaffolding**

```bash
git add pyproject.toml .python-version .gitignore src tests uv.lock
git commit -m "chore: add Python project scaffolding"
```
(`uv.lock` will exist after `uv sync` and should be tracked.)

- [ ] **Step 6.2: Commit license and changelog**

```bash
git add LICENSE CHANGELOG.md
git commit -m "chore: add license and changelog"
```

- [ ] **Step 6.3: Commit contributor guides and templates**

```bash
git add README.md CONTRIBUTING.md .github
git commit -m "chore: add contributor guides and templates"
```

- [ ] **Step 6.4: Commit pre-commit hooks**

```bash
git add .pre-commit-config.yaml
git commit -m "chore: add pre-commit hooks"
```

- [ ] **Step 6.5: Verify clean tree and history**

Run:
```bash
git status
git log --oneline
```
Expected: `nothing to commit, working tree clean`. Log shows the design-doc commit + four scaffold commits on top of `19fb3d9`.

---

## Task 7: Push and open the PR

- [ ] **Step 7.1: Push the branch**

```bash
git push -u origin chore/initial-scaffold
```

- [ ] **Step 7.2: Open the PR with `gh`**

Use a HEREDOC for the body, filled out per the PR template:

```bash
gh pr create --base main --title "chore: initial repository scaffold" --body "$(cat <<'EOF'
## What changed
Bootstrap pr-narrator as an installable Python 3.11+ CLI managed by `uv`. The CLI is wired up but only prints a version stub; no feature code yet.

Commits in this PR:
- `docs: add scaffold design spec` — design doc under `docs/superpowers/specs/`.
- `chore: add Python project scaffolding` — `pyproject.toml` (hatchling, ruff/mypy/pytest/coverage/commitizen config), `src/pr_narrator/` package with `__version__` and Click CLI, `tests/` skeleton, `.python-version`, `.gitignore`, `uv.lock`.
- `chore: add license and changelog` — Apache-2.0 `LICENSE` (© 2026 Nagendra) and Keep-a-Changelog `CHANGELOG.md`.
- `chore: add contributor guides and templates` — `CONTRIBUTING.md`, placeholder `README.md`, `.github/PULL_REQUEST_TEMPLATE.md`, and YAML issue forms for bug reports and feature requests.
- `chore: add pre-commit hooks` — `.pre-commit-config.yaml` wiring ruff (lint + format), mypy, file-hygiene hooks, and commitizen for commit-msg validation.

## Why
Stand up the repository with conventions, tooling, and contributor guardrails in place so subsequent sessions can focus on CI and feature work without revisiting scaffolding.

## How tested
- [x] `uv sync --all-extras` — clean
- [x] `uv run pytest` — 2 passed (version + CLI)
- [x] `uv run ruff check .` — clean
- [x] `uv run ruff format --check .` — clean
- [x] `uv run mypy src/` — clean
- [x] `uv run pre-commit validate-config` — clean
- [x] `uv run pr-narrator` — prints \`pr-narrator v0.0.1\`, exits 0

## Linked issues
None — first scaffold of the repository.

## Breaking changes
- [ ] This PR introduces a breaking change

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 7.3: Capture and print the PR URL**

`gh pr create` prints the URL on success. Echo it back to the user verbatim.

---

## Self-Review

- **Spec coverage:** Every section from the design doc is mapped to a task — pyproject (T1), package + tests (T1), license/changelog (T2), README/CONTRIBUTING/.github (T3), pre-commit (T4), verification (T5), commits (T6), PR (T7). ✅
- **Placeholders:** None. Every step has concrete content or commands. ✅
- **Type/name consistency:** Package name `pr-narrator` (PEP 503), Python module `pr_narrator`, CLI entry `pr-narrator = pr_narrator.cli:main`, `__version__` resolved via `importlib.metadata.version("pr-narrator")` — consistent throughout. ✅
- **Verification commands** match between Task 1, Task 5, and the PR body's "How tested" checklist. ✅
