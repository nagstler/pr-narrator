<p align="center">
  <img src="docs/assets/banner.png" alt="pr-narrator" width="720">
</p>

<p align="center">
  <a href="https://github.com/nagstler/pr-narrator/actions/workflows/test.yml"><img alt="CI" src="https://github.com/nagstler/pr-narrator/actions/workflows/test.yml/badge.svg?branch=main"></a>
  <a href="https://codecov.io/gh/nagstler/pr-narrator"><img alt="Coverage" src="https://codecov.io/gh/nagstler/pr-narrator/branch/main/graph/badge.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-blue">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-Apache%202.0-blue"></a>
  <img alt="PyPI" src="https://img.shields.io/badge/pypi-coming%20soon-lightgrey">
</p>

Turn long Claude Code sessions into reviewer-ready pull request descriptions. Claude writes from memory. **pr-narrator** writes from evidence.

## Why

Most pull request descriptions written by hand drift toward the diff: a list of files touched and a sentence per change. They lose the parts a reviewer actually wants — *why this approach, what was tried first, what was rejected, where the surprise lived*. The rationale exists somewhere; it's just usually in the author's head, or buried in a chat history nobody links to.

If you use Claude Code, the rationale is already on disk. Every prompt, every tool call, every "no, try the other way" is in the JSONL session transcript. pr-narrator reads that transcript alongside the branch diff, sends both to Claude, and asks for a description that actually explains the work — what you decided, what you considered and rejected, where the pivots happened. The synthesized description is grounded in evidence the reviewer can trust, because the source material is the conversation that produced the code.

This is a tool for Claude Code users specifically. If you don't run Claude Code, there's nothing here for you yet.

## When this tool is for you

It fits if:

- **You use Claude Code regularly** and want PR descriptions that reflect the actual decisions, not a polite summary of the diff.
- **You work alone or on a small team** where review context — "why did you do it this way" — matters more than convention compliance.
- **You ship to open source** where the "why" of a change is harder to communicate than the "what," and reviewers don't have your channel history.
- **You want the rationale captured before it evaporates.** The session transcript is gone the next time you `/clear`.

It probably doesn't fit if:

- You don't use Claude Code. There's no transcript to read; the tool has no input.
- You want a comprehensive automated reviewer (correctness analysis, style nits, bug finding). pr-narrator only writes the description; it doesn't review the code.
- You're looking for a thin `git diff` summarizer. pr-narrator is built around the conversation, not the patch.

## Quick start

```bash
# Install (PyPI, coming with v0.1.0)
uv tool install pr-narrator

# Inspect the most recent Claude Code session for this repo
pr-narrator inspect latest

# Synthesize a PR description from the latest session + the current branch diff
pr-narrator synthesize latest

# Or: synthesize and post the result as a draft PR in one step
pr-narrator create latest
```

`create` opens a draft PR by default so you can review the description before reviewers (or webhook bots) see it. Use `--no-draft` to skip that step. Use `--dry-run` to preview the title and body without touching the remote.

## Examples

### Synthesized markdown

A redacted excerpt of a real `pr-narrator synthesize` run on this project's branch that added `--paranoid` mode:

````markdown
<!--
change_type: feat
scope: redactor
risk_level: low
-->

## Summary

Adds an opt-in `--paranoid` flag that broadens the redactor's pattern set
to cover home-directory paths, `.env`-shaped uppercase assignments, RFC
1918 private IPs, email addresses, and high-entropy 32+-char tokens.

## Approach

The default redactor stays conservative — only high-confidence patterns
that are almost never false positives. `--paranoid` layers a second
pattern group on top, gated by a Shannon-entropy check on the long-token
match so we don't redact base64-encoded image bytes embedded in tests.

## Considered and rejected

- **One pattern set with a confidence score per match.** Rejected:
  ranking false-positive risk per pattern is harder than gating the
  whole aggressive group behind a flag, and the user can always run
  with `--paranoid` if they want everything.
- **Redacting public IPs.** Rejected: public IPs in code are usually
  intentional (CDN endpoints, SDK example URLs) and redacting them
  produced noisy diffs in early testing.

## Risk

Low. Default behavior is unchanged. The new patterns are entirely
behind a flag and have direct test coverage.
````

### `--debug` output

`pr-narrator synthesize latest --debug` writes the prompt, the raw model response, and a redactions block to stderr while keeping stdout clean for piping:

```text
=== PROMPT (12,481 bytes) ===
... (system + user prompt) ...

=== RAW RESPONSE (3,204 bytes) ===
... (claude's reply, pre-parsing) ...

=== REDACTIONS (4 applied) ===
- anthropic_api_key   transcript:user_message@01:24   bytes 1840-1894
- generic_secret      diff:src/config.py:42           bytes 7218-7258
- jwt                 transcript:tool_result@03:11    bytes 9602-9710
- generic_secret      transcript:assistant@04:55      bytes 11214-11256
```

The block lists category and location only — never the secret value.

### Dry run

`--dry-run` synthesizes the description and writes it straight to stdout — no `git push`, no GitHub API call, no PR created. It's the safest way to preview what `pr-narrator create` would post:

```bash
# Preview the body that would be posted, then bail out.
pr-narrator create latest --dry-run

# Or capture it for inspection / piping into your own tooling.
pr-narrator create latest --dry-run > /tmp/pr-body.md
```

## Configuration

Most users never touch a flag. The ones that matter:

- `--paranoid` — broaden redaction to include `/Users/`-style paths, env-shaped assignments, private IPs, emails, and high-entropy tokens. Default is conservative.
- `--strict` — fail synthesis if the model's frontmatter is missing required fields, instead of falling back to a partial title.
- `--dry-run` — for `create` only. Show the PR that *would* be created, including title and base, without pushing or calling the GitHub API.
- `--debug` — print the full prompt, raw response, byte counts, and any redactions to stderr. Useful when an output looks off and you want to know whether the synthesizer or the source material is responsible.

`pr-narrator <command> --help` lists everything else.

## How it works

`pr-narrator inspect` discovers and parses Claude Code's per-session JSONL files into typed events. `pr-narrator synthesize` compresses those events into a deterministic timeline (decisions, tool bursts, errors, pivots), captures the branch diff via `git`, runs both through the redactor, and asks `claude -p` to render a markdown PR description plus YAML frontmatter for downstream review bots. `pr-narrator create` does all of the above and then posts the result as a draft PR via `gh`.

For a deeper architecture writeup, see [`docs/architecture.md`](docs/architecture.md) (placeholder, landing post-v0.1).

## Security and privacy

Session transcripts and diffs routinely contain secrets in real-world use: pasted API keys, environment dumps, JWTs in error output, hardcoded credentials in early-development code. pr-narrator runs every input through a redaction layer before it reaches the LLM, and re-scans the model's response on the way out (defense in depth). The default pattern set targets high-confidence formats — Anthropic / OpenAI / AWS / GitHub / Slack / Stripe keys, JWTs, database URLs with embedded credentials, PEM private-key headers. `--paranoid` adds aggressive patterns at the cost of more false positives.

This is best-effort. We don't claim parity with [gitleaks](https://github.com/gitleaks/gitleaks) or [detect-secrets](https://github.com/Yelp/detect-secrets), and novel key formats will slip through. **Always review synthesized output before publishing.** That's why `create` defaults to a draft PR — it's a review checkpoint before the description is visible to reviewers or webhook consumers.

The full pattern list and rationale lives in [`CONTRIBUTING.md`'s Security model section](CONTRIBUTING.md#security-model). To report a vulnerability, see [`SECURITY.md`](SECURITY.md).

## Limitations

- **Claude Code is required.** There's no transcript without it. pr-narrator complements Claude Code; it doesn't replace it.
- **Synthesis quality depends on the Claude API.** Outages and quota limits surface as errors from `pr-narrator synthesize`. Auth is whatever Claude Code is configured with — pr-narrator adds no env-var requirements of its own.
- **Redaction is pattern-based.** It catches what we've taught it to catch. Audit before publishing.
- **Tested most heavily on Python projects.** The transcript format is language-agnostic and the diff capture is plain `git`, so other languages should work, but most usage and test fixtures so far are Python.
- **Single-branch focus.** `synthesize` and `create` operate on the current branch vs. a base. Multi-branch or stacked-diff workflows aren't first-class yet.

## Contributing

Issues, PRs, and design discussion are all welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, commit conventions, the local dev setup with `uv`, and the release process.

## License

[Apache License 2.0](LICENSE).

## Acknowledgments

Built with Claude Code, including its own development. The PR that opened this README was written by pr-narrator.
