"""Command-line entry point for pr-narrator."""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime

import click

from pr_narrator import __version__
from pr_narrator.discovery import (
    SessionMeta,
    find_latest_session,
    find_session_by_id,
)
from pr_narrator.errors import AmbiguousMatchError, SessionNotFoundError
from pr_narrator.parser import (
    AssistantTurn,
    Event,
    MetaEvent,
    UserMessage,
    parse_session,
)


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
