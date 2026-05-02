<p align="center">
  <img width="2244" height="701" alt="image" src="https://github.com/user-attachments/assets/3f988d79-5f9e-4e53-b80a-ec5f1849d6d8" />
</p>

<p align="center">
  <a href="https://github.com/nagstler/pr-narrator/actions/workflows/test.yml"><img alt="CI" src="https://github.com/nagstler/pr-narrator/actions/workflows/test.yml/badge.svg?branch=main"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-blue">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-Apache%202.0-blue"></a>
  <img alt="PyPI" src="https://img.shields.io/badge/pypi-coming%20soon-lightgrey">
</p>

Turn long Claude Code sessions into reviewer-ready pull request descriptions.

pr-narrator reads your Claude Code transcript, combines it with your git diff, and generates a structured PR description grounded in the actual session.

For short sessions, asking Claude in-session works fine. For long sessions, context gets compacted and the rationale disappears from active memory. pr-narrator reads the raw transcript on disk, so it works from the full session, uncompacted.

## Installation

```bash
uv tool install pr-narrator
```

Requires `claude`, `git`, and `gh` on your PATH.

## Usage

```bash
pr-narrator inspect latest          # show what's in the most recent session
pr-narrator synthesize latest       # generate a PR description
pr-narrator create latest           # synthesize and open a draft PR
```

To work from a specific session:

```bash
pr-narrator synthesize from 02ff271d
```

The session ID is a UUID prefix; pr-narrator matches the shortest unambiguous prefix.

## Example

Given a branch where you added retry logic to an HTTP client, plus a Claude Code session where you discussed why you chose exponential backoff over a fixed delay and rejected adding the `tenacity` dependency, `pr-narrator synthesize latest` produces:
```markdown
> ## What changed
>
> Adds exponential backoff retry to `http_client.py` for transient 5xx responses. Three retries with 100ms / 400ms / 1.6s delays.
>
> ## Approach
>
> Wraps the existing `request()` method rather than introducing a new client class — keeps the call sites unchanged.
>
> ## Considered & rejected
>
> - **A third-party retry library (tenacity).** Adds a dependency for what is ~30 lines of code.
> - **Fixed-delay retry.** Doesn't help with thundering-herd scenarios.
>
> ## Risk
>
> Low. Existing call sites are unchanged.
````

## Options

```
--paranoid          broaden redaction to include home paths, env-shaped lines,
                    private IPs, emails, and high-entropy tokens
--strict            fail synthesis if the model's frontmatter is incomplete
--dry-run           preview the PR without posting (create only)
--debug             print prompt, raw response, and redactions to stderr
--no-frontmatter    omit the YAML metadata block
--no-draft          open as a regular PR instead of a draft (create only)
--base BRANCH       base branch for the diff (default: main)
```

`pr-narrator <command> --help` for the full list.

## How it works

pr-narrator parses Claude Code's per-session JSONL files into typed events, compresses them into a deterministic timeline, captures the branch diff, runs both through a redactor, and asks `claude -p` to render markdown plus YAML frontmatter for downstream review bots.

Inputs and outputs pass through a redactor; see [`SECURITY.md`](SECURITY.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Development

```bash
git clone https://github.com/nagstler/pr-narrator
cd pr-narrator
uv sync --all-extras
uv run pytest
uv run pr-narrator --help
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, commit conventions, and the release process.

## License

[Apache License 2.0](LICENSE).
