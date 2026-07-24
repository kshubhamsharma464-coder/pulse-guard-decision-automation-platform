"""AI Engineering Log — event schema, redaction, and Markdown generation."""

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

MAX_TEXT_LENGTH = 500

REDACTION_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "sk-[REDACTED]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.I), "Bearer [REDACTED]"),
    (re.compile(r"(?i)(password|passwd|secret|token|api_key|apikey)\s*=\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)(password|passwd|secret|token|api_key|apikey)\s*:\s*\S+"), r"\1: [REDACTED]"),
]


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
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                handle.write(line + "\n")
                handle.flush()
            finally:
                handle.seek(0, 2)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                handle.write(line + "\n")
                handle.flush()
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_event(event: LogEvent) -> None:
    append_jsonl_line(event.to_json())
    generate_markdown_summary()


def load_session_state() -> dict[str, Any]:
    if not SESSION_STATE_PATH.exists():
        return {}
    try:
        return json.loads(SESSION_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_session_state(state: dict[str, Any]) -> None:
    SESSION_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _event_time_label(timestamp: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%H:%M")
    except ValueError:
        return timestamp


def _event_date_label(timestamp: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return "Unknown"


def format_event_markdown(event: LogEvent) -> str:
    time_label = _event_time_label(event.timestamp)
    title = event.event_type.replace("_", " ").title()
    lines = [f"### {time_label} — {title}", f"- **Summary:** {event.summary}"]

    details = event.details
    if event.event_type == "search":
        if details.get("tool"):
            lines.append(f"- **Tool:** {details['tool']}")
        if details.get("query"):
            lines.append(f"- **Query:** `{details['query']}`")
        if details.get("path"):
            lines.append(f"- **Path:** `{details['path']}`")
        if "match_count" in details:
            lines.append(f"- **Results:** {details['match_count']} matches")
    elif event.event_type == "read":
        if details.get("file_path"):
            lines.append(f"- **File:** `{details['file_path']}`")
        if details.get("line_range"):
            lines.append(f"- **Lines:** {details['line_range']}")
    elif event.event_type == "edit":
        if details.get("file_path"):
            lines.append(f"- **File:** `{details['file_path']}`")
        if details.get("operation"):
            lines.append(f"- **Operation:** {details['operation']}")
    elif event.event_type == "shell":
        if details.get("command"):
            lines.append(f"- **Command:** `{details['command']}`")
        if "exit_code" in details:
            lines.append(f"- **Exit code:** {details['exit_code']}")
    elif event.event_type == "prompt":
        if details.get("message"):
            lines.append(f"- **User:** {details['message']}")
    elif event.event_type == "response":
        if details.get("summary"):
            lines.append(f"- **Agent:** {details['summary']}")
    elif event.event_type == "task":
        if details.get("subagent_type"):
            lines.append(f"- **Subagent:** {details['subagent_type']}")
        if details.get("description"):
            lines.append(f"- **Task:** {details['description']}")
    elif event.event_type == "mcp":
        if details.get("server"):
            lines.append(f"- **Server:** {details['server']}")
        if details.get("tool_name"):
            lines.append(f"- **Tool:** {details['tool_name']}")
    elif event.event_type == "session_start":
        if details.get("project_root"):
            lines.append(f"- **Project:** `{details['project_root']}`")
    elif event.event_type == "session_end":
        if "duration_seconds" in details:
            lines.append(f"- **Duration:** {details['duration_seconds']}s")
        if "total_events" in details:
            lines.append(f"- **Events this session:** {details['total_events']}")

    return "\n".join(lines)


def generate_markdown_summary() -> None:
    events = read_all_events()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# AI Engineering Log",
        "",
        "> Auto-generated from `logs/ai-engineering-log.jsonl`. Do not edit manually.",
        f"> Last updated: {now}",
        "",
    ]

    if not events:
        lines.append("_No events recorded yet._")
    else:
        by_date: dict[str, list[LogEvent]] = {}
        for event in events:
            by_date.setdefault(_event_date_label(event.timestamp), []).append(event)

        for date_label in sorted(by_date.keys(), reverse=True):
            lines.append(f"## {date_label}")
            lines.append("")
            for event in by_date[date_label]:
                lines.append(format_event_markdown(event))
                lines.append("")

    counts = Counter(event.event_type for event in events)
    lines.extend(
        [
            "---",
            "",
            "## Statistics",
            "",
            "| Metric | Count |",
            "|--------|-------|",
            f"| Total events | {len(events)} |",
            f"| Searches | {counts.get('search', 0)} |",
            f"| Reads | {counts.get('read', 0)} |",
            f"| Edits | {counts.get('edit', 0)} |",
            f"| Shell commands | {counts.get('shell', 0)} |",
            f"| Prompts | {counts.get('prompt', 0)} |",
            f"| Responses | {counts.get('response', 0)} |",
            f"| Tasks | {counts.get('task', 0)} |",
            f"| MCP calls | {counts.get('mcp', 0)} |",
            "",
        ]
    )

    MARKDOWN_PATH.write_text("\n".join(lines), encoding="utf-8")
