"""Prompt templates and rendering/truncation helpers for the synthesizer."""

# Long lines in this module are LLM-visible prompt content, not Python
# source we should wrap. Disable line-length checks file-wide.
# ruff: noqa: E501

from __future__ import annotations

import fnmatch

from pr_narrator.compressor import CompressedEntry, CompressedTranscript

DIFF_BYTE_BUDGET: int = 40_960
TIMELINE_BYTE_BUDGET: int = 20_480
TIMELINE_HEAD_BUDGET: int = 12_288
TIMELINE_TAIL_BUDGET: int = 6_144

DIFF_SKIP_PATTERNS: tuple[str, ...] = (
    "*.lock",
    "*.lockb",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "uv.lock",
    "poetry.lock",
    "Cargo.lock",
    "go.sum",
    "*.min.js",
    "*.min.css",
)
DIFF_SKIP_PREFIXES: tuple[str, ...] = ("dist/",)

SYSTEM_PROMPT: str = """You are pr-narrator. Your job is to write a clear, evidence-grounded GitHub pull request description from a Claude Code session transcript and a git diff.

You write for two audiences:
- Human reviewers, who skim. They need to understand what changed, why, and what to look for.
- Automated review bots (CodeRabbit, Greptile), who parse structured metadata.

Hard rules:
- Only describe what's actually in the diff or transcript. Do not invent rationale.
- When the transcript shows a decision (chose X over Y, pivoted from A to B), surface it. These are the parts a reviewer can't recover from the diff alone.
- When you don't know something, say "not specified in the session" rather than guessing.
- Keep the markdown body under 500 words.

Output format (exactly this structure):

<!-- pr-narrator-meta
change_type: [feat|fix|refactor|chore|docs|test|ci|perf]
scope: <one-word area, e.g. "parser", "cli", "ci">
risk_level: [low|medium|high]
files_touched: <count>
considered_alternatives: <true|false>
-->

## What changed
<prose, 2-4 sentences>

## Why
<prose, 1-3 sentences. Reference decisions from the transcript when present>

## Approach
<prose, 2-4 sentences. How you solved it>

## Considered & rejected
<bulleted list IF the transcript shows alternatives that were considered. Otherwise omit this section entirely>

## Risk
<prose, 1-2 sentences. What could go wrong, what reviewers should look at carefully>
"""

USER_PROMPT_TEMPLATE: str = """Branch: {branch}

Commit messages on this branch:
{commit_messages}

Files changed: {changed_files_count}
{changed_files_list}

--- COMPRESSED SESSION TRANSCRIPT ---
Duration: {duration_seconds}s
User intents (verbatim):
{user_intent_chain}

Tool usage: {tool_call_summary}

Timeline:
{timeline_rendered}

--- GIT DIFF ---
{diff}

Generate the PR description now. Output ONLY the HTML comment frontmatter and the markdown sections — no preamble, no closing remarks.
"""


def parse_diff_into_files(diff: str) -> list[tuple[str, str]]:
    """Split a unified diff at `diff --git` boundaries.

    Returns a list of (path, hunk_text). Path comes from the `b/` side.
    """
    if not diff.strip():
        return []
    blocks = diff.split("\ndiff --git ")
    out: list[tuple[str, str]] = []
    for i, raw in enumerate(blocks):
        if not raw:
            continue
        header_block = raw if i == 0 and raw.startswith("diff --git ") else "diff --git " + raw
        first_line = header_block.split("\n", 1)[0]
        parts = first_line.split(" b/", 1)
        path = parts[1].strip() if len(parts) == 2 else "unknown"
        out.append((path, header_block))
    return out


def _matches_skip(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in DIFF_SKIP_PREFIXES):
        return True
    name = path.rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(path, pat) for pat in DIFF_SKIP_PATTERNS
    )


def truncate_diff(diff: str, byte_budget: int = DIFF_BYTE_BUDGET) -> tuple[str, list[str]]:
    """Skip lockfile/build-output blocks, then UTF-8 byte tail-truncate."""
    notes: list[str] = []
    blocks = parse_diff_into_files(diff)
    if not blocks:
        return diff, notes

    skipped: list[str] = []
    kept: list[str] = []
    for path, hunk in blocks:
        if _matches_skip(path):
            skipped.append(path)
        else:
            kept.append(hunk)
    if skipped:
        notes.append(f"Lockfiles/build-output skipped: {', '.join(skipped)}")

    body = "\n".join(kept) if len(kept) > 1 else (kept[0] if kept else "")
    body_bytes = body.encode("utf-8")
    if len(body_bytes) <= byte_budget:
        return body, notes

    truncated = body_bytes[:byte_budget].decode("utf-8", errors="ignore")
    omitted = len(body_bytes) - byte_budget
    truncated = truncated.rstrip() + f"\n[... diff tail truncated: {omitted} bytes omitted ...]"
    notes.append(f"Diff tail truncated: {omitted} bytes omitted")
    return truncated, notes


def _format_offset(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _render_entry(entry: CompressedEntry) -> str:
    return f"[+{_format_offset(entry.timestamp_offset)}] ({entry.kind}) {entry.text}"


def render_timeline(
    entries: list[CompressedEntry],
    byte_budget: int = TIMELINE_BYTE_BUDGET,
    head_budget: int = TIMELINE_HEAD_BUDGET,
    tail_budget: int = TIMELINE_TAIL_BUDGET,
) -> tuple[str, list[str]]:
    """Render entries with head/tail truncation at entry boundaries."""
    if not entries:
        return "", []

    rendered = [_render_entry(e) for e in entries]
    full = "\n".join(rendered)
    if len(full.encode("utf-8")) <= byte_budget:
        return full, []

    head_lines: list[str] = []
    head_bytes = 0
    head_idx = 0
    for line in rendered:
        line_bytes = len((line + "\n").encode("utf-8"))
        if head_bytes + line_bytes > head_budget:
            break
        head_lines.append(line)
        head_bytes += line_bytes
        head_idx += 1

    tail_lines: list[str] = []
    tail_bytes = 0
    tail_idx = len(rendered)
    for line in reversed(rendered[head_idx:]):
        line_bytes = len((line + "\n").encode("utf-8"))
        if tail_bytes + line_bytes > tail_budget:
            break
        tail_lines.append(line)
        tail_bytes += line_bytes
        tail_idx -= 1

    tail_lines.reverse()
    omitted_count = tail_idx - head_idx
    if omitted_count <= 0:
        return full, []

    annotation = f"[... timeline middle truncated: {omitted_count} entries omitted ...]"
    rendered_text = "\n".join([*head_lines, annotation, *tail_lines])
    notes = [f"Timeline middle truncated: {omitted_count} entries omitted"]
    return rendered_text, notes


def render_user_prompt(
    compressed: CompressedTranscript,
    diff: str,
    changed_files: list[str],
    commit_messages: list[str],
    branch: str,
) -> tuple[str, list[str]]:
    """Render the user prompt and collect truncation notes."""
    truncation_notes: list[str] = []

    truncated_diff, diff_notes = truncate_diff(diff)
    truncation_notes.extend(diff_notes)

    timeline_rendered, timeline_notes = render_timeline(compressed.timeline)
    truncation_notes.extend(timeline_notes)

    commits_block = "\n".join(f"- {m}" for m in commit_messages) if commit_messages else "(none)"
    files_block = "\n".join(f"- {f}" for f in changed_files) if changed_files else "(none)"
    intents_block = (
        "\n".join(f"- {m}" for m in compressed.user_intent_chain)
        if compressed.user_intent_chain
        else "(none)"
    )
    tool_summary_block = (
        ", ".join(f"{k}={v}" for k, v in sorted(compressed.tool_call_summary.items()))
        if compressed.tool_call_summary
        else "(none)"
    )

    rendered = USER_PROMPT_TEMPLATE.format(
        branch=branch,
        commit_messages=commits_block,
        changed_files_count=len(changed_files),
        changed_files_list=files_block,
        duration_seconds=compressed.duration_seconds,
        user_intent_chain=intents_block,
        tool_call_summary=tool_summary_block,
        timeline_rendered=timeline_rendered or "(empty)",
        diff=truncated_diff or "(empty)",
    )

    if truncation_notes:
        rendered += (
            "\n--- TRUNCATION NOTES ---\n" + "\n".join(f"- {n}" for n in truncation_notes) + "\n"
        )

    return rendered, truncation_notes
