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
