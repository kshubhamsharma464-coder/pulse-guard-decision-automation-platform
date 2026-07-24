"""AI Engineering Log — event schema, classification, and structured Markdown generation."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
JSONL_PATH = PROJECT_ROOT / "logs" / "ai-engineering-log.jsonl"
MARKDOWN_PATH = PROJECT_ROOT / "AI_ENGINEERING_LOG.md"
SESSION_STATE_PATH = Path(__file__).resolve().parent / ".session_state.json"

PROJECT_NAME = "PulseGuard"
AI_PLATFORM = "Cursor IDE / Claude / GPT"

MAX_TEXT_LENGTH = 500

REDACTION_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "sk-[REDACTED]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.I), "Bearer [REDACTED]"),
    (re.compile(r"(?i)(password|passwd|secret|token|api_key|apikey)\s*=\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)(password|passwd|secret|token|api_key|apikey)\s*:\s*\S+"), r"\1: [REDACTED]"),
]

REJECTION_PROMPT = re.compile(
    r"\b(no[,]?|instead|don't|dont|wrong|incorrect|not what i|use python|use node|"
    r"change to|modify|revert|reject|different approach|not like this|don't want)\b",
    re.I,
)
BUG_PROMPT = re.compile(
    r"\b(bug|error|broken|fail(ed|ure|s)?|issue|doesn't work|does not work|"
    r"not working|crash|exception|fix the|fix this|introduced)\b",
    re.I,
)
VALIDATION_PROMPT = re.compile(r"\b(test if|verify|validate|check if|make sure|run test|ensure)\b", re.I)
VALIDATION_SHELL = re.compile(
    r"\b(pytest|unittest|npm test|yarn test|jest|vitest|lint|ruff|eslint|mypy|"
    r"regenerate|test_ai_log|test\.py|verify|validate)\b",
    re.I,
)
LINT_TOOLS = {"ReadLints"}


@dataclass
class LogEvent:
    id: str
    timestamp: str
    session_id: str
    event_type: str
    actor: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogEvent:
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            session_id=data.get("session_id", "unknown"),
            event_type=data["event_type"],
            actor=data.get("actor", "agent"),
            summary=data["summary"],
            details=data.get("details", {}),
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def generate_event_id() -> str:
    now = datetime.now(timezone.utc)
    return f"evt_{now.strftime('%Y%m%d_%H%M%S')}_{now.microsecond:06d}"


def truncate_text(text: str, limit: int = MAX_TEXT_LENGTH) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def redact_secrets(text: str) -> str:
    result = text
    for pattern, replacement in REDACTION_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def format_timestamp(timestamp: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return timestamp


def ensure_log_dir() -> None:
    JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)


def read_all_events() -> list[LogEvent]:
    if not JSONL_PATH.exists():
        return []

    events: list[LogEvent] = []
    for line in JSONL_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(LogEvent.from_dict(json.loads(line)))
        except (json.JSONDecodeError, KeyError):
            continue
    return events


def append_jsonl_line(line: str) -> None:
    ensure_log_dir()
    with JSONL_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()


def append_event(event: LogEvent) -> None:
    append_jsonl_line(event.to_json())
    generate_narrative_markdown()


def load_session_state() -> dict[str, Any]:
    if not SESSION_STATE_PATH.exists():
        return {}
    try:
        return json.loads(SESSION_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_session_state(state: dict[str, Any]) -> None:
    SESSION_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _tool_from_event(event: LogEvent) -> str | None:
    details = event.details
    if event.event_type == "search":
        return details.get("tool")
    if event.event_type == "edit":
        return details.get("tool")
    if event.event_type == "task":
        return f"Task ({details.get('subagent_type', 'subagent')})"
    if event.event_type == "mcp":
        return f"MCP:{details.get('server', '?')}/{details.get('tool_name', '?')}"
    if event.event_type == "tool":
        return details.get("tool")
    if event.event_type in {"shell", "validation", "tool_failure"}:
        return "Shell"
    if event.event_type == "read":
        return "Read"
    return None


def _collect_ai_tools(events: list[LogEvent]) -> list[str]:
    counts: Counter[str] = Counter()
    for event in events:
        if event.event_type in {"session_start", "session_end"}:
            continue
        tool = _tool_from_event(event)
        if tool:
            counts[tool] += 1
    lines: list[str] = []
    for tool, count in counts.most_common():
        uses = "use" if count == 1 else "uses"
        lines.append(f"- **{tool}** — {count} {uses}")
    return lines or ["- _No AI tools recorded yet._"]


def _collect_key_prompts(events: list[LogEvent]) -> list[str]:
    lines: list[str] = []
    index = 1
    for event in events:
        if event.event_type != "prompt":
            continue
        message = event.details.get("message") or event.summary
        ts = format_timestamp(event.timestamp)
        lines.append(f"{index}. *{ts}* — \"{message}\"")
        index += 1
    return lines or ["- _No prompts recorded yet._"]


def _collect_code_accepted(events: list[LogEvent]) -> list[str]:
    lines: list[str] = []
    for event in events:
        if event.event_type == "code_accepted":
            path = event.details.get("file_path", "unknown")
            ts = format_timestamp(event.timestamp)
            tool = event.details.get("tool", "Write")
            lines.append(f"- `{path}` — accepted via **{tool}** ({ts})")
            if event.details.get("validation"):
                lines.append(f"  - Validated by: {event.details['validation']}")
        elif event.event_type == "edit" and event.details.get("code_status") in {"accepted", "validated"}:
            path = event.details.get("file_path", "unknown")
            op = event.details.get("operation", "update")
            ts = format_timestamp(event.timestamp)
            tool = event.details.get("tool", "Write")
            lines.append(f"- `{path}` — {op} via **{tool}** ({ts})")
            if event.details.get("validation"):
                lines.append(f"  - Validated by: {event.details['validation']}")
    return lines or ["- _No accepted AI-generated code recorded yet._"]


def _collect_code_rejected(events: list[LogEvent]) -> list[str]:
    lines: list[str] = []
    for event in events:
        if event.event_type == "edit" and event.details.get("code_status") in {"rejected", "modified"}:
            path = event.details.get("file_path", "unknown")
            status = event.details.get("code_status")
            reason = event.details.get("rejection_reason") or event.details.get("modification_reason") or "User requested changes"
            ts = format_timestamp(event.timestamp)
            label = "Rejected" if status == "rejected" else "Modified"
            lines.append(f"- `{path}` — **{label}** ({ts})")
            lines.append(f"  - **Reason:** {reason}")
        elif event.event_type == "code_rejection":
            path = event.details.get("file_path", "unknown")
            reason = event.details.get("reason", "User rejected AI output")
            ts = format_timestamp(event.timestamp)
            lines.append(f"- `{path}` — **Rejected** ({ts})")
            lines.append(f"  - **Reason:** {reason}")
    return lines or ["- _No rejected or modified AI code recorded yet._"]


def _collect_validations(events: list[LogEvent]) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for event in events:
        if event.event_type == "validation":
            desc = event.details.get("description") or event.summary
            if desc in seen:
                continue
            seen.add(desc)
            method = event.details.get("method", "manual")
            outcome = event.details.get("outcome", "completed")
            ts = format_timestamp(event.timestamp)
            lines.append(f"- *{ts}* — **{method}**: {desc} → _{outcome}_")
        elif event.event_type == "shell" and event.details.get("is_validation"):
            cmd = event.details.get("command", "")
            if cmd in seen:
                continue
            seen.add(cmd)
            exit_code = event.details.get("exit_code")
            outcome = "passed" if exit_code in (0, None) else f"failed (exit {exit_code})"
            ts = format_timestamp(event.timestamp)
            lines.append(f"- *{ts}* — **Test/Lint run**: `{cmd}` → _{outcome}_")
        elif event.event_type == "prompt" and event.details.get("is_validation_request"):
            ts = format_timestamp(event.timestamp)
            message = event.details.get("message") or event.summary
            lines.append(f"- *{ts}* — **Manual validation request**: \"{truncate_text(message, 120)}\"")
    return lines or ["- _No validation activity recorded yet._"]


def _collect_bugs_and_resolutions(events: list[LogEvent]) -> list[str]:
    lines: list[str] = []
    for event in events:
        if event.event_type == "ai_bug":
            issue = event.details.get("issue") or event.summary
            ts = format_timestamp(event.timestamp)
            source = event.details.get("source", "unknown")
            lines.append(f"- *{ts}* — **Issue** ({source}): {issue}")
            resolution = event.details.get("resolution")
            if resolution:
                lines.append(f"  - **Resolution:** {resolution}")
        elif event.event_type == "bug_resolution":
            ts = format_timestamp(event.timestamp)
            issue = event.details.get("issue", "Unknown issue")
            resolution = event.details.get("resolution") or event.summary
            lines.append(f"- *{ts}* — **Issue:** {issue}")
            lines.append(f"  - **Resolution:** {resolution}")
        elif event.event_type == "tool_failure":
            tool = event.details.get("tool", "tool")
            error = event.details.get("error") or event.summary
            ts = format_timestamp(event.timestamp)
            lines.append(f"- *{ts}* — **Tool failure** ({tool}): {truncate_text(error, 160)}")
            resolution = event.details.get("resolution")
            if resolution:
                lines.append(f"  - **Resolution:** {resolution}")
    return lines or ["- _No AI-introduced bugs or issues recorded yet._"]


def generate_narrative_markdown() -> None:
    events = read_all_events()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# AI Engineering Log",
        "",
        "## Overview",
        f"This log documents how Generative AI ({AI_PLATFORM}) was leveraged as a true **Pair Programming** "
        f"partner throughout the development of **{PROJECT_NAME}**.",
        "",
        "Rather than using AI to generate a single-file prototype, AI was strictly instructed to adhere to "
        "**Enterprise Engineering Standards** (Clean Architecture, SOLID principles, and comprehensive test coverage).",
        "",
        f"> Auto-generated from `logs/ai-engineering-log.jsonl` via Python Cursor hooks. Last updated: {now}",
        "",
        "---",
        "",
        "## AI Tools Used",
        "",
        *_collect_ai_tools(events),
        "",
        "---",
        "",
        "## Key Prompts Provided",
        "",
        *_collect_key_prompts(events),
        "",
        "---",
        "",
        "## AI-Generated Code Accepted",
        "",
        *_collect_code_accepted(events),
        "",
        "---",
        "",
        "## AI-Generated Code Rejected or Modified",
        "",
        *_collect_code_rejected(events),
        "",
        "---",
        "",
        "## How AI Outputs Were Validated",
        "",
        *_collect_validations(events),
        "",
        "---",
        "",
        "## Bugs or Issues Introduced by AI & Resolutions",
        "",
        *_collect_bugs_and_resolutions(events),
        "",
        "---",
        "",
        "## Summary",
        "",
        "The AI was used to multiply the output of a Principal Engineer — not to produce throwaway prototypes. "
        "This log tracks every tool invocation, key prompt, code acceptance decision, validation step, "
        "and bug resolution to maintain full transparency over AI-assisted development.",
        "",
    ]

    MARKDOWN_PATH.write_text("\n".join(lines), encoding="utf-8")
