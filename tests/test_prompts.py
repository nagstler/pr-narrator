"""Tests for prompts module: rendering and truncation."""

from __future__ import annotations

from pr_narrator.compressor import CompressedEntry, CompressedTranscript
from pr_narrator.prompts import (
    DIFF_BYTE_BUDGET,
    SYSTEM_PROMPT,
    parse_diff_into_files,
    render_timeline,
    render_user_prompt,
    truncate_diff,
)


def _make_diff_block(path: str, body: str = "+ added line\n- removed line\n") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"index 0000000..1111111 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,1 +1,1 @@\n"
        f"{body}"
    )


def test_truncate_diff_skips_lockfiles_by_name() -> None:
    diff = _make_diff_block("uv.lock") + _make_diff_block("src/main.py")
    out, notes = truncate_diff(diff)
    assert "uv.lock" not in out
    assert "src/main.py" in out
    assert any("uv.lock" in n for n in notes)


def test_truncate_diff_skips_min_js_and_min_css_by_glob() -> None:
    diff = (
        _make_diff_block("static/app.min.js")
        + _make_diff_block("static/app.min.css")
        + _make_diff_block("src/foo.py")
    )
    out, notes = truncate_diff(diff)
    assert "min.js" not in out
    assert "min.css" not in out
    assert "src/foo.py" in out
    assert any("min.js" in n for n in notes)


def test_truncate_diff_skips_dist_prefix() -> None:
    diff = _make_diff_block("dist/bundle.js") + _make_diff_block("src/foo.py")
    out, _ = truncate_diff(diff)
    assert "dist/bundle.js" not in out
    assert "src/foo.py" in out


def test_truncate_diff_no_skip_no_truncate_emits_no_notes() -> None:
    diff = _make_diff_block("src/foo.py")
    out, notes = truncate_diff(diff)
    assert notes == []
    assert "src/foo.py" in out


def test_truncate_diff_tail_truncates_when_over_budget() -> None:
    big_body = "+ X" * (DIFF_BYTE_BUDGET // 3 + 5000)
    diff = _make_diff_block("src/big.py", body=big_body + "\n")
    out, notes = truncate_diff(diff)
    assert "diff tail truncated" in out
    assert any("Diff tail truncated" in n for n in notes)
    assert len(out.encode("utf-8")) <= DIFF_BYTE_BUDGET + 200


def test_truncate_diff_counts_utf8_bytes_not_chars() -> None:
    body = "+ " + ("é" * (DIFF_BYTE_BUDGET // 2 + 1000)) + "\n"
    diff = _make_diff_block("src/u.py", body=body)
    out, _ = truncate_diff(diff)
    assert len(out.encode("utf-8")) <= DIFF_BYTE_BUDGET + 200


def test_truncate_diff_idempotent() -> None:
    diff = _make_diff_block("src/foo.py") * 200
    once, _ = truncate_diff(diff)
    twice, _ = truncate_diff(once)
    assert once == twice


def test_truncate_diff_at_exact_budget_does_not_annotate() -> None:
    header = (
        "diff --git a/src/exact.py b/src/exact.py\n"
        "index 0000000..1111111 100644\n"
        "--- a/src/exact.py\n"
        "+++ b/src/exact.py\n"
        "@@ -1,1 +1,1 @@\n"
    )
    pad_needed = DIFF_BYTE_BUDGET - len(header.encode("utf-8")) - len("\n")
    padding = "+" + ("a" * (pad_needed - 1)) + "\n"
    diff = header + padding
    assert len(diff.encode("utf-8")) == DIFF_BYTE_BUDGET
    out, notes = truncate_diff(diff)
    assert notes == []
    assert "diff tail truncated" not in out


def _entries(n: int, text_size: int = 100) -> list[CompressedEntry]:
    return [
        CompressedEntry(timestamp_offset=i, kind="user", text="x" * text_size) for i in range(n)
    ]


def test_render_timeline_empty_returns_empty_string() -> None:
    out, notes = render_timeline([])
    assert out == ""
    assert notes == []


def test_render_timeline_no_truncation_under_budget() -> None:
    entries = _entries(5)
    out, notes = render_timeline(entries)
    assert notes == []
    assert out.count("\n") == 4  # 5 lines


def test_render_timeline_head_tail_split_when_over_budget() -> None:
    entries = _entries(500, text_size=200)
    out, notes = render_timeline(entries)
    assert any("middle truncated" in n for n in notes)
    assert "[... timeline middle truncated:" in out
    assert out.startswith("[+00:00]")


def test_render_timeline_truncates_at_entry_boundaries_only() -> None:
    entries = _entries(500, text_size=200)
    out, _ = render_timeline(entries)
    for line in out.splitlines():
        if not line:
            continue
        if line.startswith("[..."):
            continue
        assert line.startswith("[+"), f"partial entry: {line[:50]!r}"


def test_render_user_prompt_includes_all_inputs() -> None:
    compressed = CompressedTranscript(
        timeline=[CompressedEntry(timestamp_offset=0, kind="user", text="hi")],
        tool_call_summary={"Edit": 3, "Read": 1},
        user_intent_chain=["the user intent"],
        duration_seconds=42,
        meta={},
    )
    out, notes = render_user_prompt(
        compressed=compressed,
        diff="diff --git a/x b/x\nindex 0..1 100644\n--- a/x\n+++ b/x\n+ line\n",
        changed_files=["x", "y"],
        commit_messages=["feat: a", "fix: b"],
        branch="feat/synthesizer",
    )
    assert "feat/synthesizer" in out
    assert "Files changed: 2" in out
    assert "feat: a" in out
    assert "fix: b" in out
    assert "the user intent" in out
    assert "Edit=3" in out
    assert "Read=1" in out
    assert "diff --git" in out
    assert notes == []


def test_render_user_prompt_with_truncation_appends_notes() -> None:
    compressed = CompressedTranscript(
        timeline=[],
        tool_call_summary={},
        user_intent_chain=[],
        duration_seconds=0,
        meta={},
    )
    diff = _make_diff_block("uv.lock") + _make_diff_block("src/foo.py")
    out, notes = render_user_prompt(
        compressed=compressed,
        diff=diff,
        changed_files=[],
        commit_messages=[],
        branch="b",
    )
    assert any("uv.lock" in n for n in notes)
    assert "TRUNCATION NOTES" in out


def test_render_user_prompt_empty_inputs_yield_none_placeholders() -> None:
    compressed = CompressedTranscript()
    out, _ = render_user_prompt(
        compressed=compressed,
        diff="",
        changed_files=[],
        commit_messages=[],
        branch="b",
    )
    # All sections show "(none)" / "(empty)" rather than blank
    assert "(none)" in out
    assert "(empty)" in out


def test_parse_diff_into_files_handles_empty_input() -> None:
    assert parse_diff_into_files("") == []
    assert parse_diff_into_files("   \n") == []


def test_parse_diff_into_files_splits_multiple_blocks() -> None:
    diff = _make_diff_block("a.py") + _make_diff_block("b.py")
    blocks = parse_diff_into_files(diff)
    paths = [p for p, _ in blocks]
    assert paths == ["a.py", "b.py"]


def test_parse_diff_into_files_malformed_header_falls_back_to_unknown() -> None:
    diff = "diff --git malformed_no_b_path\n@@ -1,1 +1,1 @@\n+ x\n"
    blocks = parse_diff_into_files(diff)
    assert blocks == [("unknown", diff)]


def test_parse_diff_into_files_skips_empty_split_remnants() -> None:
    # Leading newline + diff header → split produces empty first chunk.
    diff = "\ndiff --git a/x b/x\nindex 0..1 100644\n--- a/x\n+++ b/x\n+ line\n"
    blocks = parse_diff_into_files(diff)
    assert len(blocks) == 1
    assert blocks[0][0] == "x"


def test_render_timeline_head_consumes_everything_when_head_budget_huge() -> None:
    # All entries fit within head_budget → for-loop exits normally (no break).
    entries = [CompressedEntry(timestamp_offset=i, kind="user", text="x" * 600) for i in range(2)]
    out, notes = render_timeline(entries, byte_budget=1_000, head_budget=10_000, tail_budget=10_000)
    assert notes == []
    assert "[... timeline middle truncated:" not in out


def test_render_timeline_omitted_count_zero_returns_full() -> None:
    # Two entries that together exceed byte_budget, but each fits cleanly
    # in head_budget or tail_budget — head and tail together cover all
    # entries with no middle to omit.
    entries = [
        CompressedEntry(timestamp_offset=0, kind="user", text="a" * 5800),
        CompressedEntry(timestamp_offset=1, kind="user", text="b" * 5800),
    ]
    out, notes = render_timeline(entries, byte_budget=10_000, head_budget=8_000, tail_budget=8_000)
    # head consumes entry 0 (one entry fits 8000 budget); tail consumes
    # entry 1 → omitted_count == 0 → return full, no notes.
    assert notes == []
    assert "[... timeline middle truncated:" not in out


def test_system_prompt_forbids_invented_rejection_rationales() -> None:
    # Anti-fabrication rule under "Hard rules" — added after a real
    # synthesis run hallucinated a rationale not present in the
    # transcript. Asserting the wording so future edits don't
    # accidentally drop it.
    assert (
        "quote or closely paraphrase the actual rejection rationale from the transcript"
        in SYSTEM_PROMPT
    )
    assert "rationale not specified in the session" in SYSTEM_PROMPT


def test_system_prompt_includes_good_bad_worked_example() -> None:
    # Worked example under "Considered & rejected" pairs a GOOD and BAD
    # phrasing for the same rejected technology, teaching the model to
    # source rationale from the transcript rather than its own priors.
    assert "GOOD:" in SYSTEM_PROMPT
    assert "BAD:" in SYSTEM_PROMPT
    assert "Don't invent technical rationales the transcript didn't discuss" in SYSTEM_PROMPT
