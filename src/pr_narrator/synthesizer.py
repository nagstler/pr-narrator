"""LLM orchestration: render prompt, invoke `claude -p`, parse response.

pr-narrator delegates auth entirely to Claude Code. Whatever auth the
user has working with `claude` interactively (OAuth, API key, or
enterprise backends like Bedrock or Vertex) will work here. We add no
env var requirements.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pr_narrator.compressor import CompressedTranscript
from pr_narrator.errors import ClaudeBinaryNotFoundError, SynthesisError
from pr_narrator.prompts import SYSTEM_PROMPT, render_user_prompt

CHANGE_TYPE_ENUM = frozenset({"feat", "fix", "refactor", "chore", "docs", "test", "ci", "perf"})
RISK_LEVEL_ENUM = frozenset({"low", "medium", "high"})

CHANGE_TYPE_NORMALIZATION: dict[str, str] = {
    "feature": "feat",
    "bugfix": "fix",
    "bug": "fix",
    "chore-deps": "chore",
    "documentation": "docs",
    "tests": "test",
    "refactoring": "refactor",
    "perf-improvement": "perf",
}
RISK_LEVEL_NORMALIZATION: dict[str, str] = {
    "lo": "low",
    "med": "medium",
    "mid": "medium",
    "hi": "high",
}

REQUIRED_FRONTMATTER_KEYS: tuple[str, ...] = ("change_type", "risk_level")
OPTIONAL_FRONTMATTER_KEYS: tuple[str, ...] = (
    "scope",
    "files_touched",
    "considered_alternatives",
)
FRONTMATTER_OPEN = "<!-- pr-narrator-meta"
FRONTMATTER_CLOSE = "-->"


@dataclass(frozen=True)
class SynthesisResult:
    markdown: str
    frontmatter: dict[str, Any] | None
    frontmatter_complete: bool
    raw_response: str
    prompt: str
    model: str
    cost_estimate_usd: Decimal | None
    truncation_notes: list[str] = field(default_factory=list)
    synthesized_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict (handles Decimal and datetime)."""
        return {
            "markdown": self.markdown,
            "frontmatter": self.frontmatter,
            "frontmatter_complete": self.frontmatter_complete,
            "raw_response": self.raw_response,
            "prompt": self.prompt,
            "model": self.model,
            "cost_estimate_usd": str(self.cost_estimate_usd)
            if self.cost_estimate_usd is not None
            else None,
            "truncation_notes": list(self.truncation_notes),
            "synthesized_at": self.synthesized_at.isoformat(),
        }


def _parse_frontmatter_block(block: str) -> dict[str, str]:
    """Manual flat key:value parser. Forgiving on whitespace."""
    out: dict[str, str] = {}
    for raw in block.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key:
            out[key] = value
    return out


def _coerce_int(v: str) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _coerce_bool(v: str) -> bool | None:
    lower = v.strip().lower()
    if lower in {"true", "yes", "1"}:
        return True
    if lower in {"false", "no", "0"}:
        return False
    return None


def _validate_frontmatter(raw: dict[str, str]) -> tuple[dict[str, Any] | None, bool]:
    """Apply Tier 1/2/3 validation. Returns (frontmatter_or_none, complete)."""
    if not raw:
        return None, False

    coerced: dict[str, Any] = {}

    ct = raw.get("change_type", "").strip().lower()
    ct = CHANGE_TYPE_NORMALIZATION.get(ct, ct)
    if ct in CHANGE_TYPE_ENUM:
        coerced["change_type"] = ct
    else:
        return None, False

    rl = raw.get("risk_level", "").strip().lower()
    rl = RISK_LEVEL_NORMALIZATION.get(rl, rl)
    if rl in RISK_LEVEL_ENUM:
        coerced["risk_level"] = rl
    else:
        return None, False

    if raw.get("scope"):
        coerced["scope"] = raw["scope"].strip()

    if raw.get("files_touched"):
        ft = _coerce_int(raw["files_touched"])
        if ft is not None:
            coerced["files_touched"] = ft

    if raw.get("considered_alternatives"):
        ca = _coerce_bool(raw["considered_alternatives"])
        if ca is not None:
            coerced["considered_alternatives"] = ca

    return coerced, True


def _split_response(text: str) -> tuple[dict[str, str] | None, str]:
    """Locate the frontmatter HTML comment and split body off it."""
    open_idx = text.find(FRONTMATTER_OPEN)
    if open_idx < 0:
        return None, text
    after_open = text[open_idx + len(FRONTMATTER_OPEN) :]
    close_idx = after_open.find(FRONTMATTER_CLOSE)
    if close_idx < 0:
        return None, text
    block = after_open[:close_idx]
    body = after_open[close_idx + len(FRONTMATTER_CLOSE) :].lstrip("\n")
    return _parse_frontmatter_block(block), body


def synthesize_pr_description(
    compressed: CompressedTranscript,
    diff: str,
    changed_files: list[str],
    commit_messages: list[str],
    branch: str,
    claude_binary: str = "claude",
    model: str = "sonnet",
    timeout_seconds: int = 120,
    strict: bool = False,
) -> SynthesisResult:
    """Render prompt, invoke `claude -p`, parse response into SynthesisResult."""
    user_prompt, truncation_notes = render_user_prompt(
        compressed=compressed,
        diff=diff,
        changed_files=changed_files,
        commit_messages=commit_messages,
        branch=branch,
    )

    argv = [
        claude_binary,
        "-p",
        "--output-format",
        "json",
        "--no-session-persistence",
        "--tools",
        "",
        "--system-prompt",
        SYSTEM_PROMPT,
        "--model",
        model,
    ]

    try:
        completed = subprocess.run(
            argv,
            input=user_prompt,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ClaudeBinaryNotFoundError(
            "Claude Code (`claude` CLI) is not installed or not on PATH. "
            "pr-narrator requires Claude Code; install from https://claude.com/claude-code"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SynthesisError(f"claude -p timed out after {timeout_seconds}s") from exc

    if completed.returncode != 0:
        raise SynthesisError(f"claude -p exited {completed.returncode}: {completed.stderr.strip()}")

    raw_response = completed.stdout
    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise SynthesisError(f"claude -p returned non-JSON output: {raw_response[:200]}") from exc

    if not isinstance(data, dict):
        raise SynthesisError(f"claude -p returned non-object JSON: {raw_response[:200]}")

    if data.get("is_error") is True:
        subtype = data.get("subtype") or "unknown"
        raise SynthesisError(
            f"claude -p reported error (subtype: {subtype}). Raw response: {raw_response[:200]}..."
        )

    result_text = data.get("result")
    if not isinstance(result_text, str) or not result_text.strip():
        raise SynthesisError(f"claude -p response missing or empty `result`: {raw_response[:200]}")

    raw_frontmatter, body = _split_response(result_text)
    if raw_frontmatter is None:
        frontmatter: dict[str, Any] | None = None
        complete = False
    else:
        frontmatter, complete = _validate_frontmatter(raw_frontmatter)

    if strict and not complete:
        raise SynthesisError("Frontmatter validation failed in strict mode")

    cost: Decimal | None = None
    cost_raw = data.get("cost_usd")
    if cost_raw is not None:
        try:
            cost = Decimal(str(cost_raw))
        except ArithmeticError:
            cost = None

    response_model_raw = data.get("model")
    response_model = response_model_raw if isinstance(response_model_raw, str) else model

    return SynthesisResult(
        markdown=result_text.strip(),
        frontmatter=frontmatter,
        frontmatter_complete=complete,
        raw_response=raw_response,
        prompt=f"{SYSTEM_PROMPT}\n---\n{user_prompt}",
        model=response_model,
        cost_estimate_usd=cost,
        truncation_notes=list(truncation_notes),
    )
