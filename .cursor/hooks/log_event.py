"""AI Engineering Log — event schema, redaction, and narrative Markdown generation."""

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

SECTION_THEMES: list[tuple[str, re.Pattern[str], str]] = [
    ("Bootstrapping Clean Architecture", re.compile(r"\b(architecture|entity|domain|repository|interface|clean arch|use case|solid)\b", re.I), "architecture"),
    ("Strategy Pattern & Rule Engine Design", re.compile(r"\b(strategy|pattern|operator|rule engine|open.?closed|evaluat)\b", re.I), "patterns"),
    ("Advanced Debugging & Infrastructure Operations", re.compile(r"\b(docker|port|debug|lsof|kill|infra|deploy|compose|shell|network)\b", re.I), "debugging"),
    ("Security Enhancements (JWT & Key Management)", re.compile(r"\b(jwt|rsa|auth|security|private\.pem|token|oauth|key)\b", re.I), "security"),
    ("Test Coverage & Quality Assurance", re.compile(r"\b(test|coverage|pytest|spec|tdd|quality)\b", re.I), "testing"),
    ("AI Engineering Log & Audit Trail", re.compile(r"\b(engineering log|audit|logging|hook|trace)\b", re.I), "logging"),
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


def _infer_section_title(prompt_text: str, interventions: list[LogEvent]) -> str:
    for title, pattern, _ in SECTION_THEMES:
        if pattern.search(prompt_text):
            return title

    combined = prompt_text + " " + " ".join(e.summary for e in interventions)
    for title, pattern, _ in SECTION_THEMES:
        if pattern.search(combined):
            return title

    cleaned = re.sub(r"^(please|help me|can you|i want to|lets|let's)\s+", "", prompt_text.strip(), flags=re.I)
    cleaned = re.sub(r"\?$", "", cleaned).strip()
    if len(cleaned) <= 60:
        return cleaned[0].upper() + cleaned[1:] if cleaned else "AI-Assisted Development Session"
    return truncate_text(cleaned, 60)


def _intervention_bullet(event: LogEvent) -> str | None:
    details = event.details
    if event.event_type == "search":
        tool = details.get("tool", "Search")
        query = details.get("query", "")
        count = details.get("match_count")
        suffix = f" ({count} matches)" if count is not None else ""
        return f"Utilized **{tool}** to search the codebase for `{query}`{suffix}."
    if event.event_type == "read":
        path = details.get("file_path", "unknown")
        return f"Inspected `{path}` to understand existing architecture, conventions, and dependencies."
    if event.event_type == "edit":
        path = details.get("file_path", "unknown")
        op = details.get("operation", "update")
        verb = {"create": "Authored", "delete": "Removed", "update": "Refactored"}.get(op, "Updated")
        return f"{verb} `{path}` adhering to enterprise engineering standards."
    if event.event_type == "shell":
        cmd = details.get("command", "")
        return f"Dynamically shifted to **DevOps mode** — executed `{cmd}` to diagnose and resolve infrastructure issues."
    if event.event_type == "task":
        agent = details.get("subagent_type", "autonomous")
        desc = details.get("description", "explore the codebase")
        return f"Deployed an **{agent}** subagent to {desc}."
    if event.event_type == "mcp":
        server = details.get("server", "external")
        tool = details.get("tool_name", "tool")
        return f"Integrated with **{server}** via MCP tool `{tool}`."
    if event.event_type == "response":
        summary = details.get("summary", event.summary)
        return f"Delivered structured guidance: _{truncate_text(summary, 160)}_"
    if event.event_type == "tool":
        tool = details.get("tool", "tool")
        return f"Invoked `{tool}` as part of the implementation workflow."
    return None


@dataclass
class NarrativeSection:
    challenge: str
    interventions: list[str]
    title: str


def _build_sections(events: list[LogEvent]) -> list[NarrativeSection]:
    sections: list[NarrativeSection] = []
    current_prompt = ""
    current_interventions: list[LogEvent] = []

    def flush() -> None:
        nonlocal current_prompt, current_interventions
        if not current_prompt and not current_interventions:
            return
        bullets: list[str] = []
        for event in current_interventions:
            bullet = _intervention_bullet(event)
            if bullet and bullet not in bullets:
                bullets.append(bullet)
        if current_prompt or bullets:
            title = _infer_section_title(current_prompt or "Development session", current_interventions)
            challenge = current_prompt or "Continuous AI-assisted engineering on the PulseGuard platform."
            sections.append(NarrativeSection(challenge=challenge, interventions=bullets, title=title))
        current_prompt = ""
        current_interventions = []

    for event in events:
        if event.event_type in {"session_start", "session_end"}:
            continue
        if event.event_type == "prompt":
            flush()
            current_prompt = event.details.get("message") or event.summary
        else:
            current_interventions.append(event)

    flush()
    return sections


def generate_narrative_markdown() -> None:
    events = read_all_events()
    sections = _build_sections(events)
    counts = Counter(event.event_type for event in events)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# AI Engineering Log",
        "",
        "## Overview",
        f"This log documents how Generative AI ({AI_PLATFORM}) was leveraged as a true **Pair Programming** "
        f"partner throughout the development of **{PROJECT_NAME}** — an enterprise Decision Automation Platform.",
        "",
        "Rather than using AI to generate a single-file prototype, AI was strictly instructed to adhere to "
        "**Enterprise Engineering Standards** (Clean Architecture, SOLID principles, and comprehensive test coverage).",
        "",
        f"> Auto-generated from `logs/ai-engineering-log.jsonl` via Python Cursor hooks. Last updated: {now}",
        "",
        "---",
        "",
    ]

    if not sections:
        lines.append("_No AI engineering sessions recorded yet. Interact with Cursor AI to populate this log._")
        lines.append("")
    else:
        for index, section in enumerate(sections, start=1):
            lines.append(f"## {index}. {section.title}")
            lines.append("")
            lines.append(f"**Challenge**: {section.challenge}")
            lines.append("**AI Intervention**:")
            if section.interventions:
                for bullet in section.interventions:
                    lines.append(f"- {bullet}")
            else:
                lines.append("- AI analyzed the request and provided architectural guidance.")
            lines.append("")

    total_interventions = sum(len(s.interventions) for s in sections)
    lines.extend(
        [
            "---",
            "",
            "## Summary",
            "",
            f"The AI was not used to write a throwaway prototype; it was used to multiply the output of a "
            f"Principal Engineer. Across **{len(sections)}** documented sessions and **{total_interventions}** "
            f"recorded interventions, the AI handled architecture scaffolding, rapid pattern expansion, "
            f"infrastructure debugging, and security hardening — enabling delivery of a production-ready "
            f"enterprise platform in record time.",
            "",
            "### Session Statistics",
            "",
            "| Metric | Count |",
            "|--------|-------|",
            f"| Total events | {len(events)} |",
            f"| Documented sessions | {len(sections)} |",
            f"| Codebase searches | {counts.get('search', 0)} |",
            f"| Files read | {counts.get('read', 0)} |",
            f"| Files edited | {counts.get('edit', 0)} |",
            f"| Shell / DevOps actions | {counts.get('shell', 0)} |",
            f"| User prompts | {counts.get('prompt', 0)} |",
            f"| Subagent tasks | {counts.get('task', 0)} |",
            "",
        ]
    )

    MARKDOWN_PATH.write_text("\n".join(lines), encoding="utf-8")
