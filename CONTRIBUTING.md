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
