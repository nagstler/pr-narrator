"""Tests for the rule-based transcript compressor."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from pr_narrator.compressor import (
    DECISION_KEYWORDS,
    CompressedTranscript,
    compress,
)
from pr_narrator.parser import (
    AssistantTurn,
    Event,
    MetaEvent,
    ToolCall,
    ToolResult,
    UserMessage,
    parse_session,
)

T0 = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)


def _at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


def test_empty_stream_returns_empty_transcript() -> None:
    result = compress([])
    assert result.timeline == []
    assert result.tool_call_summary == {}
    assert result.user_intent_chain == []
    assert result.duration_seconds == 0
    assert result.meta == {}


def test_user_messages_preserved_verbatim_in_chain_and_timeline() -> None:
    events: list[Event] = [
        UserMessage(timestamp=_at(0), content="Implement feature X", uuid="u1"),
        UserMessage(timestamp=_at(30), content="Also handle edge case Y", uuid="u2"),
    ]

    result = compress(events)

    assert result.user_intent_chain == [
        "Implement feature X",
        "Also handle edge case Y",
    ]
    user_entries = [e for e in result.timeline if e.kind == "user"]
    assert [e.text for e in user_entries] == [
        "Implement feature X",
        "Also handle edge case Y",
    ]
    assert [e.timestamp_offset for e in user_entries] == [0, 30]
    assert result.duration_seconds == 30


def test_assistant_decisions_kept_pure_narration_dropped() -> None:
    events: list[Event] = [
        AssistantTurn(
            timestamp=_at(10),
            text_blocks=["Now I'll edit the file."],
            tool_calls=[],
            uuid="a1",
        ),
        AssistantTurn(
            timestamp=_at(20),
            text_blocks=["I chose Click over argparse for the CLI."],
            tool_calls=[],
            uuid="a2",
        ),
    ]

    result = compress(events)
    decision_entries = [e for e in result.timeline if e.kind == "decision"]
    assert len(decision_entries) == 1
    assert "Click over argparse" in decision_entries[0].text
    assert decision_entries[0].timestamp_offset == 10  # 20 - 10 (origin)


def test_each_decision_keyword_detected() -> None:
    for kw in DECISION_KEYWORDS:
        events: list[Event] = [
            AssistantTurn(
                timestamp=_at(0),
                text_blocks=[f"We {kw} this approach for clarity."],
                tool_calls=[],
                uuid="x",
            ),
        ]
        result = compress(events)
        assert any(e.kind == "decision" for e in result.timeline), kw


def test_tool_burst_collapses_above_threshold() -> None:
    edits = [ToolCall(tool_name="Edit", tool_input={}, tool_use_id=f"e{i}") for i in range(5)]
    events: list[Event] = [
        AssistantTurn(timestamp=_at(0), text_blocks=[], tool_calls=edits, uuid="a"),
    ]
    result = compress(events)
    bursts = [e for e in result.timeline if e.kind == "tool_burst"]
    assert len(bursts) == 1
    assert "5" in bursts[0].text
    assert "Edit" in bursts[0].text
    assert result.tool_call_summary == {"Edit": 5}


def test_tool_calls_below_threshold_render_individually() -> None:
    reads = [ToolCall(tool_name="Read", tool_input={"file_path": "/x"}, tool_use_id="r1")]
    events: list[Event] = [
        AssistantTurn(timestamp=_at(0), text_blocks=[], tool_calls=reads, uuid="a"),
    ]
    result = compress(events)
    individuals = [e for e in result.timeline if e.kind == "tool_call"]
    assert len(individuals) == 1
    assert "Read" in individuals[0].text


def test_text_block_breaks_burst() -> None:
    edits1 = [ToolCall(tool_name="Edit", tool_input={}, tool_use_id=f"e{i}") for i in range(2)]
    edits2 = [ToolCall(tool_name="Edit", tool_input={}, tool_use_id=f"f{i}") for i in range(2)]
    events: list[Event] = [
        AssistantTurn(timestamp=_at(0), text_blocks=[], tool_calls=edits1, uuid="a"),
        AssistantTurn(
            timestamp=_at(1),
            text_blocks=["I chose to refactor."],
            tool_calls=edits2,
            uuid="b",
        ),
    ]
    result = compress(events)
    assert sum(1 for e in result.timeline if e.kind == "tool_call") == 4
    assert sum(1 for e in result.timeline if e.kind == "tool_burst") == 0
    decision_idxs = [i for i, e in enumerate(result.timeline) if e.kind == "decision"]
    assert len(decision_idxs) == 1


def test_tool_error_preserved_as_error_entry() -> None:
    call = ToolCall(tool_name="Bash", tool_input={"command": "foo"}, tool_use_id="b1")
    events: list[Event] = [
        AssistantTurn(timestamp=_at(0), text_blocks=[], tool_calls=[call], uuid="a"),
        ToolResult(tool_use_id="b1", content="command not found: foo", is_error=True),
    ]
    result = compress(events)
    errors = [e for e in result.timeline if e.kind == "error"]
    assert len(errors) == 1
    assert "Bash" in errors[0].text
    assert "command not found: foo" in errors[0].text


def test_compaction_meta_event_surfaces_in_timeline() -> None:
    events: list[Event] = [
        UserMessage(timestamp=_at(0), content="start", uuid="u"),
        MetaEvent(type="compaction", timestamp=_at(60), data={}),
        MetaEvent(type="system", timestamp=_at(70), data={}),
    ]
    result = compress(events)
    compactions = [e for e in result.timeline if e.kind == "compaction"]
    assert len(compactions) == 1
    assert compactions[0].timestamp_offset == 60
    assert result.meta == {"compaction": 1, "system": 1}


def test_excerpt_keeps_head_when_keyword_at_start() -> None:
    long_tail = " ".join(["filler sentence."] * 60)
    text = f"I chose Click. {long_tail}"
    events: list[Event] = [
        AssistantTurn(timestamp=_at(0), text_blocks=[text], tool_calls=[], uuid="a"),
    ]
    result = compress(events)
    decision = next(e for e in result.timeline if e.kind == "decision")
    assert decision.text.startswith("I chose Click")
    assert decision.text.endswith("…")
    assert not decision.text.startswith("…")


def test_excerpt_keeps_tail_when_keyword_at_end() -> None:
    long_head = " ".join(["filler sentence."] * 60)
    text = f"{long_head} I chose Click."
    events: list[Event] = [
        AssistantTurn(timestamp=_at(0), text_blocks=[text], tool_calls=[], uuid="a"),
    ]
    result = compress(events)
    decision = next(e for e in result.timeline if e.kind == "decision")
    assert decision.text.startswith("…")
    assert decision.text.rstrip("…").rstrip().endswith("I chose Click.")


def test_excerpt_keeps_middle_when_keyword_central() -> None:
    long_head = " ".join(["head sentence."] * 60)
    long_tail = " ".join(["tail sentence."] * 60)
    text = f"{long_head} I chose Click. {long_tail}"
    events: list[Event] = [
        AssistantTurn(timestamp=_at(0), text_blocks=[text], tool_calls=[], uuid="a"),
    ]
    result = compress(events)
    decision = next(e for e in result.timeline if e.kind == "decision")
    assert decision.text.startswith("…")
    assert decision.text.endswith("…")
    assert "I chose Click" in decision.text


def test_empty_text_block_yields_no_decision() -> None:
    events: list[Event] = [
        AssistantTurn(timestamp=_at(0), text_blocks=["   "], tool_calls=[], uuid="a"),
    ]
    result = compress(events)
    assert all(e.kind != "decision" for e in result.timeline)


def test_keyword_sentence_without_trailing_punctuation_kept() -> None:
    events: list[Event] = [
        AssistantTurn(
            timestamp=_at(0),
            text_blocks=["I chose Click"],  # no trailing period
            tool_calls=[],
            uuid="a",
        ),
    ]
    result = compress(events)
    assert any(e.kind == "decision" and "Click" in e.text for e in result.timeline)


def test_single_long_sentence_with_keyword_hard_trimmed() -> None:
    long_block = "We chose " + ("xx " * 500) + "in the end"
    events: list[Event] = [
        AssistantTurn(timestamp=_at(0), text_blocks=[long_block], tool_calls=[], uuid="a"),
    ]
    result = compress(events)
    decisions = [e for e in result.timeline if e.kind == "decision"]
    assert len(decisions) == 1
    # Hard-trim path → text length close to cap, ends with ellipsis.
    assert decisions[0].text.endswith("…")


def test_orphan_tool_result_ignored() -> None:
    # A ToolResult whose tool_use_id matches no current call must not crash
    # and must not register as an error entry.
    events: list[Event] = [
        ToolResult(tool_use_id="orphan-id", content="x", is_error=True),
    ]
    result = compress(events)
    assert all(e.kind != "error" for e in result.timeline)


def test_trailing_burst_flushed_at_end_of_stream() -> None:
    edits = [ToolCall(tool_name="Edit", tool_input={}, tool_use_id=f"e{i}") for i in range(4)]
    events: list[Event] = [
        AssistantTurn(timestamp=_at(0), text_blocks=[], tool_calls=edits, uuid="a"),
        # No follow-up event — burst must still be flushed.
    ]
    result = compress(events)
    assert any(e.kind == "tool_burst" for e in result.timeline)


def test_replay_against_sample_fixture_smoke() -> None:
    fixture = Path(__file__).parent / "fixtures" / "sample_session.jsonl"
    events = list(parse_session(fixture))
    result = compress(events)
    assert isinstance(result, CompressedTranscript)
    assert result.duration_seconds >= 0
    assert isinstance(result.timeline, list)
    assert len(result.user_intent_chain) >= 1
