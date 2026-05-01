"""Tests for pr_narrator.parser."""

from __future__ import annotations

import inspect as inspect_mod
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pr_narrator.parser import (
    AssistantTurn,
    Event,
    MetaEvent,
    ToolCall,
    ToolResult,
    UserMessage,
    load_session,
    parse_session,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def test_event_dataclasses_are_frozen() -> None:
    from dataclasses import FrozenInstanceError

    msg = UserMessage(timestamp=datetime(2026, 1, 1, tzinfo=UTC), content="hi", uuid="u")
    with pytest.raises(FrozenInstanceError):
        msg.content = "changed"  # type: ignore[misc]


def test_tool_call_round_trips() -> None:
    call = ToolCall(tool_name="Bash", tool_input={"cmd": "ls"}, tool_use_id="t1")
    assert call.tool_name == "Bash"
    assert call.tool_input == {"cmd": "ls"}


def test_meta_event_allows_none_timestamp() -> None:
    meta = MetaEvent(type="ai-title", timestamp=None, data={"x": 1})
    assert meta.timestamp is None


def _events_by_uuid(events: list[Event]) -> dict[str, Event]:
    out: dict[str, Event] = {}
    for e in events:
        if isinstance(e, UserMessage | AssistantTurn):
            out[e.uuid] = e
    return out


def test_parses_user_text_message() -> None:
    events = load_session(FIXTURE)
    by_uuid = _events_by_uuid(events)
    msg = by_uuid["u-0001"]
    assert isinstance(msg, UserMessage)
    assert msg.content == "fix the bug in foo.py"
    assert msg.timestamp == datetime(2026, 5, 1, 10, 0, 0, tzinfo=UTC)


def test_parses_assistant_text_only() -> None:
    events = load_session(FIXTURE)
    by_uuid = _events_by_uuid(events)
    turn = by_uuid["a-0002"]
    assert isinstance(turn, AssistantTurn)
    assert turn.text_blocks == ["Looking at foo.py now."]
    assert turn.tool_calls == []


def test_parses_assistant_tool_use() -> None:
    events = load_session(FIXTURE)
    by_uuid = _events_by_uuid(events)
    turn = by_uuid["a-0003"]
    assert isinstance(turn, AssistantTurn)
    assert turn.text_blocks == []
    assert len(turn.tool_calls) == 1
    call = turn.tool_calls[0]
    assert call.tool_name == "Read"
    assert call.tool_input == {"file_path": "/proj/foo.py"}
    assert call.tool_use_id == "toolu_01"


def test_parses_assistant_thinking_dropped() -> None:
    events = load_session(FIXTURE)
    by_uuid = _events_by_uuid(events)
    turn = by_uuid["a-0001"]
    assert isinstance(turn, AssistantTurn)
    assert turn.text_blocks == []
    assert turn.tool_calls == []


def test_parses_assistant_mixed_text_and_tool_use() -> None:
    events = load_session(FIXTURE)
    by_uuid = _events_by_uuid(events)
    turn = by_uuid["a-0006"]
    assert isinstance(turn, AssistantTurn)
    assert turn.text_blocks == ["Switching to Redis."]
    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0].tool_name == "Edit"


def test_parses_tool_result_string_content() -> None:
    events = load_session(FIXTURE)
    results = [e for e in events if isinstance(e, ToolResult)]
    first = next(r for r in results if r.tool_use_id == "toolu_01")
    assert first.content == "def foo():\n    pass"
    assert first.is_error is False


def test_parses_tool_result_block_list_content() -> None:
    events = load_session(FIXTURE)
    results = [e for e in events if isinstance(e, ToolResult)]
    second = next(r for r in results if r.tool_use_id == "toolu_02")
    assert second.content == "file edited"
    assert second.is_error is False


def test_parses_tool_result_with_error_flag() -> None:
    events = load_session(FIXTURE)
    results = [e for e in events if isinstance(e, ToolResult)]
    err = next(r for r in results if r.tool_use_id == "toolu_03")
    assert err.is_error is True
    assert err.content == "command failed"


def test_parses_tool_result_missing_is_error_defaults_false() -> None:
    events = load_session(FIXTURE)
    results = [e for e in events if isinstance(e, ToolResult)]
    fourth = next(r for r in results if r.tool_use_id == "toolu_04")
    assert fourth.is_error is False


def test_known_meta_event_preserves_type() -> None:
    events = load_session(FIXTURE)
    metas = [e for e in events if isinstance(e, MetaEvent)]
    types = {m.type for m in metas}
    assert "summary" in types
    assert "compaction" in types
    assert "attachment" in types
    assert "ai-title" in types


def test_meta_event_with_timestamp_parses_it() -> None:
    events = load_session(FIXTURE)
    metas = [e for e in events if isinstance(e, MetaEvent)]
    compaction = next(m for m in metas if m.type == "compaction")
    assert compaction.timestamp == datetime(2026, 5, 1, 10, 2, 0, tzinfo=UTC)


def test_meta_event_without_timestamp_yields_none() -> None:
    events = load_session(FIXTURE)
    metas = [e for e in events if isinstance(e, MetaEvent)]
    ai_title = next(m for m in metas if m.type == "ai-title")
    assert ai_title.timestamp is None


def test_line_without_type_field_yields_unknown_meta() -> None:
    events = load_session(FIXTURE)
    metas = [e for e in events if isinstance(e, MetaEvent)]
    unknown = next(m for m in metas if m.type == "unknown")
    assert unknown.data.get("note") == "line with no type field"


def test_malformed_json_skipped_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="pr_narrator.parser"):
        events = load_session(FIXTURE)
    assert any("Skipping malformed JSON" in rec.message for rec in caplog.records)
    assert all(not (isinstance(e, MetaEvent) and "not valid json" in str(e.data)) for e in events)


def test_blank_lines_are_skipped(tmp_path: Path) -> None:
    p = tmp_path / "blank.jsonl"
    p.write_text(
        '\n\n{"type":"user","uuid":"u","timestamp":"2026-05-01T10:00:00Z",'
        '"message":{"role":"user","content":"hi"}}\n\n',
        encoding="utf-8",
    )
    events = load_session(p)
    assert len(events) == 1
    assert isinstance(events[0], UserMessage)


def test_non_object_json_line_skipped_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    p = tmp_path / "scalar.jsonl"
    p.write_text('"just a string"\n[1,2,3]\n', encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pr_narrator.parser"):
        events = load_session(p)
    assert events == []
    assert any("non-object" in rec.message.lower() for rec in caplog.records)


def test_user_message_without_timestamp_falls_back_to_epoch(tmp_path: Path) -> None:
    p = tmp_path / "no_ts.jsonl"
    p.write_text(
        '{"type":"user","uuid":"u","message":{"role":"user","content":"hi"}}\n',
        encoding="utf-8",
    )
    events = load_session(p)
    assert isinstance(events[0], UserMessage)
    assert events[0].timestamp == datetime.fromtimestamp(0, tz=UTC)


def test_unparseable_timestamp_falls_back_to_epoch(tmp_path: Path) -> None:
    p = tmp_path / "bad_ts.jsonl"
    p.write_text(
        '{"type":"user","uuid":"u","timestamp":"not-a-date",'
        '"message":{"role":"user","content":"hi"}}\n',
        encoding="utf-8",
    )
    events = load_session(p)
    assert isinstance(events[0], UserMessage)
    assert events[0].timestamp == datetime.fromtimestamp(0, tz=UTC)


def test_parse_session_is_a_generator_function() -> None:
    assert inspect_mod.isgeneratorfunction(parse_session)


def test_parse_session_returns_an_iterator(tmp_path: Path) -> None:
    p = tmp_path / "tiny.jsonl"
    p.write_text(
        '{"type":"user","uuid":"u","timestamp":"2026-05-01T10:00:00Z",'
        '"message":{"role":"user","content":"hi"}}\n',
        encoding="utf-8",
    )
    result = parse_session(p)
    assert isinstance(result, Iterator)


def test_parse_session_streams_lazily(tmp_path: Path) -> None:
    """Reading one event must not exhaust the file."""
    p = tmp_path / "many.jsonl"
    line = (
        '{"type":"user","uuid":"u","timestamp":"2026-05-01T10:00:00Z",'
        '"message":{"role":"user","content":"hi"}}\n'
    )
    p.write_text(line * 1000, encoding="utf-8")
    gen = parse_session(p)
    first = next(gen)
    assert isinstance(first, UserMessage)
    second = next(gen)
    assert isinstance(second, UserMessage)
    gen.close()


def test_load_session_returns_list(tmp_path: Path) -> None:
    p = tmp_path / "tiny.jsonl"
    p.write_text(
        '{"type":"user","uuid":"u","timestamp":"2026-05-01T10:00:00Z",'
        '"message":{"role":"user","content":"hi"}}\n',
        encoding="utf-8",
    )
    result = load_session(p)
    assert isinstance(result, list)
    assert len(result) == 1


def test_assistant_turn_with_no_message_field_yields_empty(tmp_path: Path) -> None:
    p = tmp_path / "thin.jsonl"
    p.write_text(
        '{"type":"assistant","uuid":"a","timestamp":"2026-05-01T10:00:00Z"}\n',
        encoding="utf-8",
    )
    events = load_session(p)
    assert isinstance(events[0], AssistantTurn)
    assert events[0].text_blocks == []
    assert events[0].tool_calls == []


def test_user_message_with_text_block_list_content(tmp_path: Path) -> None:
    """A user event whose message.content is a list of text blocks (not a bare string)."""
    p = tmp_path / "block_list.jsonl"
    p.write_text(
        '{"type":"user","uuid":"u","timestamp":"2026-05-01T10:00:00Z",'
        '"message":{"role":"user","content":['
        '{"type":"text","text":"hello"},{"type":"text","text":"world"}]}}\n',
        encoding="utf-8",
    )
    events = load_session(p)
    assert isinstance(events[0], UserMessage)
    assert events[0].content == "hello\nworld"


def test_tool_result_with_non_str_non_list_content_yields_empty(tmp_path: Path) -> None:
    """When tool_result.content is neither str nor list, content stringifies to ''."""
    p = tmp_path / "weird_result.jsonl"
    p.write_text(
        '{"type":"user","uuid":"u","timestamp":"2026-05-01T10:00:00Z",'
        '"message":{"role":"user","content":[{"type":"tool_result",'
        '"tool_use_id":"t","content":null}]}}\n',
        encoding="utf-8",
    )
    events = load_session(p)
    assert isinstance(events[0], ToolResult)
    assert events[0].content == ""


def test_tool_use_with_non_dict_input_yields_empty_dict(tmp_path: Path) -> None:
    p = tmp_path / "weird_input.jsonl"
    p.write_text(
        '{"type":"assistant","uuid":"a","timestamp":"2026-05-01T10:00:00Z",'
        '"message":{"role":"assistant","content":[{"type":"tool_use","id":"t","name":"X","input":"not-a-dict"}]}}\n',
        encoding="utf-8",
    )
    events = load_session(p)
    assert isinstance(events[0], AssistantTurn)
    assert events[0].tool_calls[0].tool_input == {}
