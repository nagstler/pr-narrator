"""Parse Claude Code JSONL session files into typed events."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserMessage:
    timestamp: datetime
    content: str
    uuid: str


@dataclass(frozen=True)
class ToolCall:
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str


@dataclass(frozen=True)
class AssistantTurn:
    timestamp: datetime
    text_blocks: list[str]
    tool_calls: list[ToolCall]
    uuid: str


@dataclass(frozen=True)
class ToolResult:
    tool_use_id: str
    content: str
    is_error: bool


@dataclass(frozen=True)
class MetaEvent:
    type: str
    timestamp: datetime | None
    data: dict[str, Any]


Event = UserMessage | AssistantTurn | ToolResult | MetaEvent


def _parse_timestamp(raw: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp; return None on any failure."""
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _epoch() -> datetime:
    return datetime.fromtimestamp(0, tz=UTC)


def _content_blocks(message: Any) -> list[dict[str, Any]]:
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def _stringify_tool_result_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _user_event(line: dict[str, Any]) -> Event:
    """Map a ``type=="user"`` line to UserMessage or ToolResult."""
    raw_message = line.get("message")
    message: dict[str, Any] = raw_message if isinstance(raw_message, dict) else {}
    blocks = _content_blocks(message)
    for block in blocks:
        if block.get("type") == "tool_result":
            return ToolResult(
                tool_use_id=str(block.get("tool_use_id", "")),
                content=_stringify_tool_result_content(block.get("content")),
                is_error=bool(block.get("is_error", False)),
            )
    raw_content = message.get("content")
    if isinstance(raw_content, str):
        text = raw_content
    else:
        text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    return UserMessage(
        timestamp=_parse_timestamp(line.get("timestamp")) or _epoch(),
        content=text,
        uuid=str(line.get("uuid", "")),
    )


def _assistant_event(line: dict[str, Any]) -> AssistantTurn:
    blocks = _content_blocks(line.get("message"))
    text_blocks: list[str] = []
    tool_calls: list[ToolCall] = []
    # TODO: thinking blocks contain decision rationale that may be
    # valuable for synthesis. v0.1 drops them; revisit if PR
    # descriptions feel shallow.
    for block in blocks:
        block_type = block.get("type")
        if block_type == "text":
            text_blocks.append(str(block.get("text", "")))
        elif block_type == "tool_use":
            raw_input = block.get("input")
            tool_calls.append(
                ToolCall(
                    tool_name=str(block.get("name", "")),
                    tool_input=dict(raw_input) if isinstance(raw_input, dict) else {},
                    tool_use_id=str(block.get("id", "")),
                )
            )
    return AssistantTurn(
        timestamp=_parse_timestamp(line.get("timestamp")) or _epoch(),
        text_blocks=text_blocks,
        tool_calls=tool_calls,
        uuid=str(line.get("uuid", "")),
    )


def _meta_event(line: dict[str, Any]) -> MetaEvent:
    line_type = line.get("type")
    return MetaEvent(
        type=str(line_type) if line_type is not None else "unknown",
        timestamp=_parse_timestamp(line.get("timestamp")),
        data=line,
    )


def parse_session(path: Path) -> Iterator[Event]:
    """Stream events from a JSONL file. Yields one Event per line.

    Malformed lines are logged at WARNING level and skipped. Unknown
    ``type`` values are surfaced as MetaEvent so callers can handle
    them generically.
    """
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw_line in enumerate(fh, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                line = json.loads(stripped)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed JSON at %s:%d: %s", path, lineno, exc)
                continue
            if not isinstance(line, dict):
                logger.warning("Skipping non-object JSON at %s:%d", path, lineno)
                continue
            line_type = line.get("type")
            if line_type == "user":
                yield _user_event(line)
            elif line_type == "assistant":
                yield _assistant_event(line)
            else:
                yield _meta_event(line)


def load_session(path: Path) -> list[Event]:
    """Eagerly collect all events from ``path`` into a list."""
    return list(parse_session(path))
