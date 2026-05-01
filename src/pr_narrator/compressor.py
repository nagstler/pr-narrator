"""Deterministic, rule-based compression of Claude Code session events."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pr_narrator.parser import (
    AssistantTurn,
    Event,
    MetaEvent,
    ToolCall,
    ToolResult,
    UserMessage,
)

# Phrases whose presence in an assistant text block flags it as a
# "decision" worth preserving. "because" and "actually" were
# considered and rejected (too high recall in routine prose).
DECISION_KEYWORDS: tuple[str, ...] = (
    "decided",
    "chose",
    "pivoted",
    "going with",
    "instead of",
    "rejected",
    "won't",
    "can't",
    "switched to",
    "ended up",
    "settled on",
    "turns out",
    "opted for",
    "ruled out",
    "prefer",
)

TOOL_BURST_THRESHOLD: int = 3
ASSISTANT_BLOCK_CHAR_CAP: int = 400
COMPACTION_META_TYPES: frozenset[str] = frozenset({"compaction", "summary"})

EntryKind = Literal["user", "decision", "tool_burst", "tool_call", "error", "compaction"]


@dataclass(frozen=True)
class CompressedEntry:
    timestamp_offset: int
    kind: EntryKind
    text: str


@dataclass(frozen=True)
class CompressedTranscript:
    timeline: list[CompressedEntry] = field(default_factory=list)
    tool_call_summary: dict[str, int] = field(default_factory=dict)
    user_intent_chain: list[str] = field(default_factory=list)
    duration_seconds: int = 0
    meta: dict[str, int] = field(default_factory=dict)


def _event_timestamp(event: Event) -> datetime | None:
    if isinstance(event, UserMessage | AssistantTurn):
        return event.timestamp
    if isinstance(event, MetaEvent):
        return event.timestamp
    return None


def _origin(events: list[Event]) -> datetime | None:
    timestamps = [t for t in (_event_timestamp(e) for e in events) if t is not None]
    return min(timestamps) if timestamps else None


def _offset(ts: datetime | None, origin: datetime | None) -> int:
    if ts is None or origin is None:
        return 0
    return max(0, int((ts - origin).total_seconds()))


def _split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    for ch in text:
        buf.append(ch)
        if ch in ".!?":
            parts.append("".join(buf).strip())
            buf = []
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


def _matches_decision_keyword(sentence: str) -> bool:
    lower = sentence.lower()
    return any(kw in lower for kw in DECISION_KEYWORDS)


def _excerpt_around_keyword(text: str, cap: int = ASSISTANT_BLOCK_CHAR_CAP) -> str | None:
    sentences = _split_sentences(text)
    if not sentences:
        return None
    hit_idx: int | None = None
    for i, s in enumerate(sentences):
        if _matches_decision_keyword(s):
            hit_idx = i
            break
    if hit_idx is None:
        return None

    selected = [hit_idx]
    left = hit_idx - 1
    right = hit_idx + 1

    def _join(indices: list[int]) -> str:
        return " ".join(sentences[i] for i in sorted(indices))

    while True:
        grew = False
        if right < len(sentences):
            candidate = selected + [right]
            if len(_join(candidate)) <= cap:
                selected = candidate
                right += 1
                grew = True
        if left >= 0:
            candidate = selected + [left]
            if len(_join(candidate)) <= cap:
                selected = candidate
                left -= 1
                grew = True
        if not grew:
            break

    excerpt = _join(selected)
    cut_left = min(selected) > 0
    cut_right = max(selected) < len(sentences) - 1

    if len(excerpt) > cap:
        excerpt = excerpt[:cap]
        cut_right = True

    if cut_left and cut_right:
        return f"…{excerpt}…"
    if cut_left:
        return f"…{excerpt}"
    if cut_right:
        return f"{excerpt}…"
    return excerpt


def _tool_arg_hint(call: ToolCall) -> str:
    inp = call.tool_input
    for key in ("file_path", "path", "command", "pattern", "url"):
        v = inp.get(key)
        if isinstance(v, str) and v:
            return f" ({v})"
    return ""


def _flush_burst(
    burst: list[ToolCall],
    last_result: ToolResult | None,
    burst_offset: int,
    timeline: list[CompressedEntry],
) -> None:
    if not burst:
        return
    tool = burst[0].tool_name
    count = len(burst)
    if count >= TOOL_BURST_THRESHOLD:
        suffix = (
            "no result captured"
            if last_result is None
            else ("final call failed" if last_result.is_error else "final call succeeded")
        )
        text = f"{tool} x{count}; {suffix}"
        timeline.append(
            CompressedEntry(timestamp_offset=burst_offset, kind="tool_burst", text=text)
        )
    else:
        for call in burst:
            arg_hint = _tool_arg_hint(call)
            text = f"{tool}{arg_hint}"
            timeline.append(
                CompressedEntry(timestamp_offset=burst_offset, kind="tool_call", text=text)
            )


def compress(events: Iterable[Event]) -> CompressedTranscript:
    """Walk events once and return a CompressedTranscript."""
    event_list = list(events)
    origin = _origin(event_list)
    last_offset = 0

    timeline: list[CompressedEntry] = []
    user_intent_chain: list[str] = []
    tool_call_summary: dict[str, int] = {}
    meta: dict[str, int] = {}

    burst: list[ToolCall] = []
    burst_offset = 0
    burst_tool: str | None = None
    last_result: ToolResult | None = None
    last_call_ids: set[str] = set()
    last_assistant_offset = 0

    def flush() -> None:
        nonlocal burst, burst_tool, last_result, last_call_ids
        _flush_burst(burst, last_result, burst_offset, timeline)
        burst = []
        burst_tool = None
        last_result = None
        last_call_ids = set()

    for event in event_list:
        ts = _event_timestamp(event)
        offset = _offset(ts, origin)
        if ts is not None:
            last_offset = max(last_offset, offset)

        if isinstance(event, UserMessage):
            flush()
            timeline.append(
                CompressedEntry(timestamp_offset=offset, kind="user", text=event.content)
            )
            user_intent_chain.append(event.content)

        elif isinstance(event, AssistantTurn):
            last_assistant_offset = offset
            for block in event.text_blocks:
                excerpt = _excerpt_around_keyword(block)
                if excerpt is not None:
                    flush()
                    timeline.append(
                        CompressedEntry(timestamp_offset=offset, kind="decision", text=excerpt)
                    )
            for call in event.tool_calls:
                tool_call_summary[call.tool_name] = tool_call_summary.get(call.tool_name, 0) + 1
                if burst_tool is None:
                    burst_tool = call.tool_name
                    burst_offset = offset
                if call.tool_name != burst_tool:
                    flush()
                    burst_tool = call.tool_name
                    burst_offset = offset
                burst.append(call)
                last_call_ids.add(call.tool_use_id)

        elif isinstance(event, ToolResult):
            if event.tool_use_id in last_call_ids:
                last_result = event
                if event.is_error:
                    tool = burst_tool or "Tool"
                    snippet_src = (
                        event.content.strip().splitlines()[0] if event.content.strip() else ""
                    )
                    snippet = snippet_src[:160]
                    text = f"{tool} error: {snippet}" if snippet else f"{tool} error"
                    flush()
                    timeline.append(
                        CompressedEntry(
                            timestamp_offset=last_assistant_offset,
                            kind="error",
                            text=text,
                        )
                    )

        elif isinstance(event, MetaEvent):  # pragma: no branch
            meta[event.type] = meta.get(event.type, 0) + 1
            if event.type in COMPACTION_META_TYPES:
                flush()
                timeline.append(
                    CompressedEntry(
                        timestamp_offset=offset,
                        kind="compaction",
                        text=f"context {event.type}",
                    )
                )

    flush()

    return CompressedTranscript(
        timeline=timeline,
        tool_call_summary=tool_call_summary,
        user_intent_chain=user_intent_chain,
        duration_seconds=last_offset,
        meta=meta,
    )
