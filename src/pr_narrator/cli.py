"""Command-line entry point for pr-narrator."""

from __future__ import annotations

import json
import re
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
    GitHubCliNotFoundError,
    NotInGitRepoError,
    PRCreationError,
    PushFailedError,
    SessionNotFoundError,
    SynthesisError,
    UnknownBaseRefError,
)
from pr_narrator.github import (
    create_pr,
    get_remote_pr_for_branch,
    is_branch_on_remote,
    push_branch,
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


_CONVENTIONAL_PREFIX = re.compile(r"^(\w+)(\([^)]+\))?:\s*")

_TITLE_SKIP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^fixup!", re.IGNORECASE),
    re.compile(r"^squash!", re.IGNORECASE),
    re.compile(r"^style(\([^)]+\))?:", re.IGNORECASE),
    re.compile(r"^docs(\([^)]+\))?:", re.IGNORECASE),
    re.compile(r"^chore(\([^)]+\))?:.*format", re.IGNORECASE),
    re.compile(r"^wip(\([^)]+\))?:", re.IGNORECASE),
)


def _is_skip_commit(subject: str) -> bool:
    return any(p.search(subject) for p in _TITLE_SKIP_PATTERNS)


def _pick_title_source(commit_messages: list[str]) -> str:
    """Pick the best commit subject to seed the PR title.

    `commit_messages` is the output of ``git log base..HEAD --pretty=format:%s``,
    so it is newest-first: index 0 is the most recent commit, index -1 is the
    oldest. Walk newest -> oldest and return the first subject that isn't a
    fixup, squash, style/docs/wip commit, or a "chore: ... format ..." cleanup.
    Fall back to the newest subject when every commit matches a skip pattern.
    """
    if not commit_messages:
        return "(no commits on branch)"
    for subject in commit_messages:
        if not _is_skip_commit(subject):
            return subject
    return commit_messages[0]


def _build_pr_title(result: SynthesisResult, commit_messages: list[str]) -> str:
    """Compose a PR title from synthesis frontmatter + best-fit commit subject.

    Happy path: frontmatter has change_type and scope -> strip any leading
    conventional-commit prefix from the chosen commit subject and prepend
    f"{change_type}({scope}): ".

    Fallback: use the chosen commit subject verbatim.
    """
    source = _pick_title_source(commit_messages)
    fm = result.frontmatter
    if result.frontmatter_complete and fm is not None and "change_type" in fm and "scope" in fm:
        stripped = _CONVENTIONAL_PREFIX.sub("", source).lstrip()
        return f"{fm['change_type']}({fm['scope']}): {stripped}"
    return source


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
    if result.redactions:
        click.echo(f"=== REDACTIONS ({len(result.redactions)} applied) ===", err=True)
        for r in result.redactions:
            click.echo(
                f"- {r.category} in {r.location} @ bytes {r.span[0]}-{r.span[1]}",
                err=True,
            )
        click.echo("================================", err=True)
    click.echo("================================================", err=True)


def _run_synthesize(
    meta: SessionMeta,
    base: str,
    model: str,
    no_frontmatter: bool,
    debug: bool,
    strict: bool,
    paranoid: bool,
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
            paranoid=paranoid,
        )
    except (ClaudeBinaryNotFoundError, SynthesisError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if debug:
        _emit_debug(result)

    output = _strip_frontmatter(result.markdown) if no_frontmatter else result.markdown
    click.echo(output)


def _common_synthesize_options(func: F) -> F:
    func = click.option(
        "--paranoid",
        is_flag=True,
        help=(
            "Enable aggressive redaction (file paths, .env-shaped lines, "
            "private IPs, emails, high-entropy strings). Default mode redacts "
            "only high-confidence patterns."
        ),
    )(func)
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
    base: str,
    model: str,
    no_frontmatter: bool,
    debug: bool,
    strict: bool,
    paranoid: bool,
) -> None:
    """Synthesize a PR description for the most recent session."""
    meta = find_latest_session()
    if meta is None:
        click.echo("No Claude Code sessions found for this directory.", err=True)
        sys.exit(1)
    _run_synthesize(meta, base, model, no_frontmatter, debug, strict, paranoid)


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
    paranoid: bool,
) -> None:
    """Synthesize a PR description for the session matching the given UUID prefix."""
    try:
        meta = find_session_by_id(session_id)
    except (SessionNotFoundError, AmbiguousMatchError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    _run_synthesize(meta, base, model, no_frontmatter, debug, strict, paranoid)


# ---------------------------------------------------------------------------
# create command
# ---------------------------------------------------------------------------


@main.group()
def create() -> None:
    """Synthesize a PR description and post it via the gh CLI."""


def _common_create_options(func: F) -> F:
    func = click.option(
        "--paranoid",
        is_flag=True,
        help=(
            "Enable aggressive redaction (file paths, .env-shaped lines, "
            "private IPs, emails, high-entropy strings)."
        ),
    )(func)
    func = click.option(
        "--force-new",
        is_flag=True,
        help="Create a new PR even if one already exists for this branch",
    )(func)
    func = click.option(
        "--no-create-on-closed",
        is_flag=True,
        help="When a closed (not merged) PR exists, exit 0 instead of creating a new one",
    )(func)
    func = click.option(
        "--dry-run",
        is_flag=True,
        help="Synthesize and print, do not push or create a PR",
    )(func)
    func = click.option("--no-draft", is_flag=True, help="Create as a regular PR, not draft")(func)
    func = click.option("--strict", is_flag=True, help="Fail on any frontmatter validation issue")(
        func
    )
    func = click.option(
        "--no-frontmatter", is_flag=True, help="Strip the HTML comment frontmatter"
    )(func)
    func = click.option("--model", default="sonnet", show_default=True, help="Claude model to use")(
        func
    )
    func = click.option("--base", default="main", show_default=True, help="Base branch for the PR")(
        func
    )
    return func


def _run_create(
    meta: SessionMeta,
    base: str,
    model: str,
    no_frontmatter: bool,
    strict: bool,
    no_draft: bool,
    dry_run: bool,
    no_create_on_closed: bool,
    force_new: bool,
    paranoid: bool,
) -> None:
    try:
        branch = get_current_branch()
    except NotInGitRepoError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if branch == base:
        click.echo(f"Currently on `{base}`. Switch to a feature branch first.", err=True)
        sys.exit(1)

    if not force_new:
        try:
            existing = get_remote_pr_for_branch(branch)
        except (GitHubCliNotFoundError, PRCreationError) as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(1)
        if existing is not None:
            if existing.state == "OPEN":
                click.echo(existing.url)
                return
            if existing.state == "MERGED":
                click.echo(
                    f"Error: PR for this branch was already merged ({existing.url}). "
                    "Use a new branch.",
                    err=True,
                )
                sys.exit(1)
            if existing.state == "CLOSED" and no_create_on_closed:
                click.echo(existing.url)
                click.echo(
                    f"Closed PR exists; not creating a new one ({existing.url}).",
                    err=True,
                )
                return

    try:
        events = list(parse_session(meta.path))
        compressed = compress(events)
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
            paranoid=paranoid,
        )
    except (ClaudeBinaryNotFoundError, SynthesisError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    body = _strip_frontmatter(result.markdown) if no_frontmatter else result.markdown

    if dry_run:
        click.echo(body)
        return

    if not is_branch_on_remote(branch):
        click.echo(f"Pushing branch {branch} to origin...", err=True)
        try:
            push_branch(branch)
        except PushFailedError as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(1)

    title = _build_pr_title(result, commit_messages)

    try:
        url = create_pr(title=title, body=body, base=base, draft=not no_draft)
    except (GitHubCliNotFoundError, PRCreationError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(url)
    click.echo(f"Opened PR: {url}", err=True)


@create.command("latest")
@_common_create_options
def create_latest(
    base: str,
    model: str,
    no_frontmatter: bool,
    strict: bool,
    no_draft: bool,
    dry_run: bool,
    no_create_on_closed: bool,
    force_new: bool,
    paranoid: bool,
) -> None:
    """Create a PR from the most recent session."""
    meta = find_latest_session()
    if meta is None:
        click.echo("No Claude Code sessions found for this directory.", err=True)
        sys.exit(1)
    _run_create(
        meta,
        base,
        model,
        no_frontmatter,
        strict,
        no_draft,
        dry_run,
        no_create_on_closed,
        force_new,
        paranoid,
    )


@create.command("from")
@click.argument("session_id")
@_common_create_options
def create_from(
    session_id: str,
    base: str,
    model: str,
    no_frontmatter: bool,
    strict: bool,
    no_draft: bool,
    dry_run: bool,
    no_create_on_closed: bool,
    force_new: bool,
    paranoid: bool,
) -> None:
    """Create a PR from the session matching the given UUID prefix."""
    try:
        meta = find_session_by_id(session_id)
    except (SessionNotFoundError, AmbiguousMatchError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    _run_create(
        meta,
        base,
        model,
        no_frontmatter,
        strict,
        no_draft,
        dry_run,
        no_create_on_closed,
        force_new,
        paranoid,
    )
