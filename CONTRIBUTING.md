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

## Continuous integration

Every PR runs the following checks via GitHub Actions:

- **Test matrix** — `pytest --cov` on Python 3.11, 3.12, and 3.13 (Ubuntu)
- **Lint** — `ruff check` and `ruff format --check`
- **Type check** — `mypy src/`
- **Commit lint** — every commit and the PR title must follow Conventional Commits

All checks must pass before a PR can be merged. (Required status checks
will be enforced on `main` once this CI scaffolding lands.)

To run the same checks locally before pushing:

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src/
uv run pytest --cov=pr_narrator
```

Coverage reports upload to Codecov from the Python 3.11 leg of the matrix.

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

## Security model

pr-narrator pipes session transcripts and git diffs through
`claude -p`, then optionally posts the result as a public PR
description. Both inputs commonly contain secrets in real life:
pasted API keys, command output dumping environment variables,
JWTs in error messages, `.env` files shown via Read, hardcoded
credentials in early-development code, internal hostnames in
config. We mitigate this with two layers of redaction:

**Default (always-on) — high-confidence patterns.** Anthropic,
OpenAI, AWS, GitHub (classic and fine-grained), Slack, and Stripe
API keys; 3-segment JSON Web Tokens; database connection strings
with embedded credentials (`postgres://`, `mysql://`, `mongodb://`,
`redis://`); PEM private-key headers; and `password=`/`secret=`/
`api_key=`/`access_key=`/`auth_token=` assignments where the value
is 16+ url-safe characters.

**Opt-in (`--paranoid`) — aggressive patterns.** File paths under
`/Users/` and `/home/`; `.env`-shaped uppercase assignments;
private IPv4 addresses (RFC 1918 ranges only — public IPs are
often intentional in code); email addresses; runs of 32+ url-safe
characters that pass a Shannon-entropy threshold (~4.5 bits/char,
which separates random tokens from English text and most code
identifiers).

**What we don't claim.** This is best-effort, not comprehensive
secret detection. We don't run as a replacement for tools like
[gitleaks](https://github.com/gitleaks/gitleaks) or
[detect-secrets](https://github.com/Yelp/detect-secrets), and we
don't promise zero false negatives. Novel key formats, unusual
encodings, secrets embedded in prose, and credentials that look
like ordinary identifiers will slip through. **Always review the
synthesized output before publishing it.** This is why
`pr-narrator create` defaults to draft PRs — drafts give you a
review checkpoint before the description is visible to reviewers
or webhook consumers.

When redaction does fire, you'll see categorical placeholders like
`[REDACTED:anthropic_api_key]` in the output; run with `--debug`
to see a per-redaction listing on stderr (categories and locations
only, never the secret value).
