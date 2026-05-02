# Security policy

## Reporting a vulnerability

Please report security vulnerabilities to <placeholder for user to fill in: an email address or "open a private security advisory on GitHub">. Do not open public issues for security concerns.

We aim to respond within 5 business days.

## Scope

In scope:

- Vulnerabilities in pr-narrator's code (CLI, synthesizer, redactor, GitHub integration).
- Supply-chain vulnerabilities affecting how pr-narrator is published to PyPI.
- CI workflow misconfigurations that could enable code execution or credential exposure.

Out of scope:

- Vulnerabilities in dependencies — please report those upstream.
- Vulnerabilities in the `claude` CLI or Claude Code itself — please report those to Anthropic.
- Social engineering, phishing, or denial-of-service.
- Issues that require physical access to the reporter's machine.

## Disclosure

We follow coordinated disclosure: we'll work with you to develop and ship a patch before any public disclosure. If you'd like, we'll credit you in the `CHANGELOG` and the release notes.

## Hardening notes

pr-narrator handles two classes of sensitive input by design — Claude Code session transcripts and git diffs — both of which can contain pasted secrets, environment-variable dumps, and credentials. The redaction layer (`pr_narrator.redactor`) is documented in [`CONTRIBUTING.md`'s "Security model" section](CONTRIBUTING.md#security-model). It is best-effort and not a substitute for a dedicated secret scanner; always review synthesized output before publishing it. `pr-narrator create` defaults to draft PRs for exactly this reason.
