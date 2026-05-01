"""Command-line entry point for pr-narrator."""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar

import click

from pr_narrator import __version__
from pr_narrator.compressor import compress
from pr_narrator.diff import (
    get_branch_diff,
    get_changed_files,
    get_commit_messages,
    get_current_branch,
)
from pr_narrator.discovery import (
    SessionMeta,
    find_latest_session,
    find_session_by_id,
)
from pr_narrator.errors import (
    AmbiguousMatchError,
    ClaudeBinaryNotFoundError,
    NotInGitRepoError,
    SessionNotFoundError,
    SynthesisError,
    UnknownBaseRefError,
)
from pr_narrator.parser import (
    AssistantTurn,
    Event,
    MetaEvent,
    UserMessage,
    parse_session,
)
from pr_narrator.synthesizer import SynthesisResult, synthesize_pr_description

FRONTMATTER_OPEN_LITERAL = "<!-- pr-narrator-meta"
FRONTMATTER_CLOSE_LITERAL = "-->"

F = TypeVar("F", bound=Callable[..., Any])


@click.group()
@click.version_option(
    version=__version__,
    prog_name="pr-narrator",
    message="pr-narrator v%(version)s",
)
def main() -> None:
    """Turn Claude Code sessions into reviewer-ready PR descriptions."""


@main.group()
def inspect() -> None:
    """Inspect a Claude Code session transcript."""


@inspect.command("latest")
def inspect_latest() -> None:
    """Summarize the most recent session in the current directory."""
    meta = find_latest_session()
    if meta is None:
        click.echo("No Claude Code sessions found for this directory.", err=True)
        sys.exit(1)
    _print_summary(meta)


@inspect.command("from")
@click.argument("session_id")
def inspect_from(session_id: str) -> None:
    """Summarize the session matching the given UUID prefix."""
    try:
        meta = find_session_by_id(session_id)
    except (SessionNotFoundError, AmbiguousMatchError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    _print_summary(meta)


def _format_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f}MB"
    if n >= 1024:
        return f"{n / 1024:.0f}KB"
    return f"{n}B"


def _format_relative(ts: datetime, origin: datetime) -> str:
    seconds = max(0, int((ts - origin).total_seconds()))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _truncate(s: str, width: int = 80) -> str:
    flat = s.replace("\n", " ").strip()
    if len(flat) <= width:
        return flat
    return flat[: width - 1] + "…"


def _earliest_timestamp(events: list[Event]) -> datetime | None:
    timestamps: list[datetime] = []
    for e in events:
        if isinstance(e, UserMessage | AssistantTurn):  # noqa: SIM114
            timestamps.append(e.timestamp)
        elif isinstance(e, MetaEvent) and e.timestamp is not None:
            timestamps.append(e.timestamp)
    return min(timestamps) if timestamps else None


def _print_summary(meta: SessionMeta) -> None:
    events = list(parse_session(meta.path))
    user_msgs = [e for e in events if isinstance(e, UserMessage)]
    asst_turns = [e for e in events if isinstance(e, AssistantTurn)]
    meta_events = [e for e in events if isinstance(e, MetaEvent)]

    origin = _earliest_timestamp(events) or meta.mtime
    short_id = meta.session_id.split("-")[0]

    click.echo(
        f"SESSION: {short_id} ({_format_size(meta.size_bytes)}, "
        f"{len(events)} events, {meta.mtime.strftime('%Y-%m-%dT%H:%M:%S%z')})"
    )
    click.echo("─" * 60)

    click.echo(f"USER MESSAGES ({len(user_msgs)}):")
    for u in user_msgs:
        click.echo(f"  [{_format_relative(u.timestamp, origin)}] {_truncate(u.content)}")

    click.echo(f"ASSISTANT TURNS: {len(asst_turns)}")

    tool_counter: Counter[str] = Counter(c.tool_name for t in asst_turns for c in t.tool_calls)
    total_tools = sum(tool_counter.values())
    if total_tools:
        top = tool_counter.most_common(5)
        breakdown = ", ".join(f"{name}: {count}" for name, count in top)
        leftover = total_tools - sum(c for _, c in top)
        if leftover > 0:
            breakdown += f", +{leftover} other"
        click.echo(f"TOOL CALLS: {total_tools} ({breakdown})")
    else:
        click.echo("TOOL CALLS: 0")

    if meta_events:
        meta_counter: Counter[str] = Counter(m.type for m in meta_events)
        meta_breakdown = ", ".join(f"{t}: {c}" for t, c in meta_counter.most_common())
        click.echo(f"META EVENTS: {len(meta_events)} ({meta_breakdown})")
    else:
        click.echo("META EVENTS: 0")

    click.echo(f"TOTAL EVENTS: {len(events)}")


@main.group()
def synthesize() -> None:
    """Synthesize a PR description from a session + git diff."""


def _strip_frontmatter(markdown: str) -> str:
    open_idx = markdown.find(FRONTMATTER_OPEN_LITERAL)
    if open_idx < 0:
        return markdown
    after = markdown[open_idx + len(FRONTMATTER_OPEN_LITERAL) :]
    close_idx = after.find(FRONTMATTER_CLOSE_LITERAL)
    if close_idx < 0:
        return markdown
    return after[close_idx + len(FRONTMATTER_CLOSE_LITERAL) :].lstrip("\n")


def _emit_debug(result: SynthesisResult) -> None:
    prompt = result.prompt
    sys_prompt, _, user_prompt = prompt.partition("\n---\n")
    sys_bytes = len(sys_prompt.encode("utf-8"))
    user_bytes = len(user_prompt.encode("utf-8"))
    total_bytes = sys_bytes + user_bytes
    raw_bytes = len(result.raw_response.encode("utf-8"))

    click.echo(f"=== PROMPT (sent to claude -p, {total_bytes} bytes) ===", err=True)
    click.echo(f"<system prompt, {sys_bytes} bytes>", err=True)
    click.echo(sys_prompt, err=True)
    click.echo("---", err=True)
    click.echo(f"<user prompt, {user_bytes} bytes>", err=True)
    click.echo(user_prompt, err=True)
    click.echo(f"=== RESPONSE (claude -p JSON, {raw_bytes} bytes) ===", err=True)
    try:
        parsed = json.loads(result.raw_response)
        click.echo(json.dumps(parsed, indent=2), err=True)
    except json.JSONDecodeError:
        click.echo(result.raw_response, err=True)
    click.echo("=== TRUNCATION NOTES ===", err=True)
    if result.truncation_notes:
        for note in result.truncation_notes:
            click.echo(f"- {note}", err=True)
    else:
        click.echo("(none)", err=True)
    click.echo("=== COST ===", err=True)
    if result.cost_estimate_usd is not None:
        click.echo(f"${result.cost_estimate_usd:.4f} ({result.model})", err=True)
    else:
        click.echo(f"(unknown) ({result.model})", err=True)
    click.echo("================================================", err=True)


def _run_synthesize(
    meta: SessionMeta,
    base: str,
    model: str,
    no_frontmatter: bool,
    debug: bool,
    strict: bool,
) -> None:
    events = list(parse_session(meta.path))
    compressed = compress(events)

    try:
        branch = get_current_branch()
        diff = get_branch_diff(base=base)
        changed_files = get_changed_files(base=base)
        commit_messages = get_commit_messages(base=base)
    except (NotInGitRepoError, UnknownBaseRefError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    try:
        result = synthesize_pr_description(
            compressed=compressed,
            diff=diff,
            changed_files=changed_files,
            commit_messages=commit_messages,
            branch=branch,
            model=model,
            strict=strict,
        )
    except (ClaudeBinaryNotFoundError, SynthesisError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if debug:
        _emit_debug(result)

    output = _strip_frontmatter(result.markdown) if no_frontmatter else result.markdown
    click.echo(output)


def _common_synthesize_options(func: F) -> F:
    func = click.option("--strict", is_flag=True, help="Fail on any frontmatter validation issue")(
        func
    )
    func = click.option("--debug", is_flag=True, help="Print prompt and response to stderr")(func)
    func = click.option(
        "--no-frontmatter", is_flag=True, help="Strip the HTML comment frontmatter"
    )(func)
    func = click.option("--model", default="sonnet", show_default=True, help="Claude model to use")(
        func
    )
    func = click.option("--base", default="main", show_default=True, help="Base branch for diff")(
        func
    )
    return func


@synthesize.command("latest")
@_common_synthesize_options
def synthesize_latest(
    base: str, model: str, no_frontmatter: bool, debug: bool, strict: bool
) -> None:
    """Synthesize a PR description for the most recent session."""
    meta = find_latest_session()
    if meta is None:
        click.echo("No Claude Code sessions found for this directory.", err=True)
        sys.exit(1)
    _run_synthesize(meta, base, model, no_frontmatter, debug, strict)


@synthesize.command("from")
@click.argument("session_id")
@_common_synthesize_options
def synthesize_from(
    session_id: str,
    base: str,
    model: str,
    no_frontmatter: bool,
    debug: bool,
    strict: bool,
) -> None:
    """Synthesize a PR description for the session matching the given UUID prefix."""
    try:
        meta = find_session_by_id(session_id)
    except (SessionNotFoundError, AmbiguousMatchError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    _run_synthesize(meta, base, model, no_frontmatter, debug, strict)
