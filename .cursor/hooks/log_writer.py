#!/usr/bin/env python3
"""Cursor hook handler — append AI Engineering Log events from stdin JSON."""

from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from log_event import (  # noqa: E402
    BUG_PROMPT,
    LINT_TOOLS,
    LogEvent,
    PROJECT_ROOT,
    REJECTION_PROMPT,
    VALIDATION_PROMPT,
    VALIDATION_SHELL,
    append_event,
    generate_event_id,
    load_session_state,
    redact_secrets,
    save_session_state,
    truncate_text,
    utc_now_iso,
)

SEARCH_TOOLS = {"Grep", "WebSearch", "Glob"}
READ_TOOLS = {"Read"}
EDIT_TOOLS = {"Write", "StrReplace", "Delete"}
SHELL_TOOLS = {"Shell"}
TASK_TOOLS = {"Task"}


def read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read().lstrip("\ufeff")
    if not raw.strip():
        return {}
    return json.loads(raw)


def get_session_id(payload: dict[str, Any]) -> str:
    for key in ("conversation_id", "session_id", "chat_id", "thread_id"):
        value = payload.get(key)
        if value:
            return str(value)
    return "unknown"


def get_nested(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def get_tool_name(payload: dict[str, Any]) -> str:
    for key in ("tool_name", "toolName", "name", "tool"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    nested = get_nested(payload, "tool", "name", default="")
    return str(nested or "")


def get_tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("tool_input", "toolInput", "input", "arguments"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    nested = get_nested(payload, "tool", "input", default={})
    return nested if isinstance(nested, dict) else {}


def get_tool_output(payload: dict[str, Any]) -> Any:
    for key in ("tool_output", "toolOutput", "output", "result"):
        if key in payload:
            return payload[key]
    return get_nested(payload, "tool", "output")


def extract_prompt_text(payload: dict[str, Any]) -> str:
    for key in ("prompt", "message", "text", "user_message", "userMessage"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_response_text(payload: dict[str, Any]) -> str:
    for key in ("response", "text", "message", "content", "agent_message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_error_text(payload: dict[str, Any]) -> str:
    for key in ("error", "error_message", "errorMessage", "message", "stderr"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return truncate_text(json.dumps(payload), 200)


def count_grep_matches(output: Any) -> int | None:
    if output is None:
        return None
    text = output if isinstance(output, str) else json.dumps(output)
    if not text or "No matches found" in text:
        return 0
    matches = re.findall(r"^[^\n]+:\d+:", text, flags=re.MULTILINE)
    return len(matches) if matches else 0


def _resolve_pending_edits(state: dict[str, Any], code_status: str, reason: str) -> None:
    pending = state.get("pending_edits", [])
    if not pending:
        return
    append_event(
        LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id=state.get("session_id", "unknown"),
            event_type="code_rejection" if code_status == "rejected" else "edit",
            actor="user",
            summary=f"Code {code_status}: {pending[-1].get('file_path', 'unknown')}",
            details={
                "file_path": pending[-1].get("file_path"),
                "reason": reason,
                "code_status": code_status,
            },
        )
    )
    for item in pending:
        item["code_status"] = code_status
        if code_status == "rejected":
            item["rejection_reason"] = reason
        else:
            item["modification_reason"] = reason
    state["pending_edits"] = []


def _mark_previous_edit_modified(state: dict[str, Any], file_path: str, reason: str) -> None:
    pending = state.get("pending_edits", [])
    for item in pending:
        if item.get("file_path") == file_path and item.get("code_status") == "pending":
            item["code_status"] = "modified"
            item["modification_reason"] = reason
            append_event(
                LogEvent(
                    id=generate_event_id(),
                    timestamp=utc_now_iso(),
                    session_id=state.get("session_id", "unknown"),
                    event_type="edit",
                    actor="agent",
                    summary=f"Modified AI code in '{file_path}'",
                    details={
                        "file_path": file_path,
                        "code_status": "modified",
                        "modification_reason": reason,
                        "operation": "update",
                    },
                )
            )


def _accept_pending_edits(state: dict[str, Any], validation_note: str | None = None) -> None:
    for item in state.get("pending_edits", []):
        status = "validated" if validation_note else "accepted"
        append_event(
            LogEvent(
                id=generate_event_id(),
                timestamp=utc_now_iso(),
                session_id=state.get("session_id", "unknown"),
                event_type="code_accepted",
                actor="agent",
                summary=f"Accepted AI code in '{item.get('file_path', 'unknown')}'",
                details={
                    "file_path": item.get("file_path"),
                    "code_status": status,
                    "operation": item.get("operation", "update"),
                    "tool": item.get("tool", "Write"),
                    "validation": validation_note,
                },
            )
        )
    state["pending_edits"] = []


def build_search_event(payload: dict[str, Any], tool: str, tool_input: dict[str, Any]) -> LogEvent:
    output = get_tool_output(payload)
    if tool == "WebSearch":
        query = str(tool_input.get("search_term") or tool_input.get("query") or "")
        summary = f"Web search for '{truncate_text(query, 80)}'"
        details = {"tool": tool, "query": query}
    elif tool == "Glob":
        pattern = str(tool_input.get("glob_pattern") or tool_input.get("pattern") or "")
        path = str(tool_input.get("target_directory") or tool_input.get("path") or ".")
        match_count = len([line for line in str(output or "").splitlines() if line.strip()]) if output else None
        summary = f"Searched files matching '{truncate_text(pattern, 80)}'"
        details = {"tool": tool, "query": pattern, "path": path, "match_count": match_count}
    else:
        query = str(tool_input.get("pattern") or tool_input.get("query") or "")
        path = str(tool_input.get("path") or ".")
        summary = f"Searched codebase for '{truncate_text(query, 80)}'"
        details = {"tool": tool, "query": query, "path": path, "match_count": count_grep_matches(output)}
    return LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=get_session_id(payload),
        event_type="search",
        actor="agent",
        summary=summary,
        details=details,
    )


def build_read_event(payload: dict[str, Any], tool_input: dict[str, Any]) -> LogEvent:
    file_path = str(tool_input.get("path") or tool_input.get("file_path") or "unknown")
    return LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=get_session_id(payload),
        event_type="read",
        actor="agent",
        summary=f"Read file '{file_path}'",
        details={"file_path": file_path, "tool": "Read"},
    )


def build_edit_event(payload: dict[str, Any], tool: str, tool_input: dict[str, Any]) -> LogEvent:
    file_path = str(tool_input.get("path") or tool_input.get("file_path") or "unknown")
    if tool == "Write":
        operation = "create" if tool_input.get("contents") is not None else "update"
    elif tool == "Delete":
        operation = "delete"
    else:
        operation = "update"

    state = load_session_state()
    for item in state.get("pending_edits", []):
        if item.get("file_path") == file_path:
            _mark_previous_edit_modified(state, file_path, "AI refined the same file in a follow-up edit")
            break

    state.setdefault("pending_edits", []).append(
        {
            "file_path": file_path,
            "operation": operation,
            "tool": tool,
            "code_status": "pending",
            "timestamp": utc_now_iso(),
        }
    )
    save_session_state(state)

    return LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=get_session_id(payload),
        event_type="edit",
        actor="agent",
        summary=f"{operation.title()} file '{file_path}'",
        details={
            "file_path": file_path,
            "operation": operation,
            "tool": tool,
            "code_status": "pending",
        },
    )


def build_shell_event(payload: dict[str, Any], tool_input: dict[str, Any]) -> LogEvent:
    command = redact_secrets(str(tool_input.get("command") or ""))
    output = get_tool_output(payload)
    exit_code = output.get("exit_code") or output.get("exitCode") if isinstance(output, dict) else None
    is_validation = bool(VALIDATION_SHELL.search(command))

    if is_validation:
        state = load_session_state()
        outcome = "passed" if exit_code in (0, None) else f"failed (exit {exit_code})"
        if exit_code in (0, None) and state.get("pending_edits"):
            _accept_pending_edits(state, validation_note=f"`{truncate_text(command, 80)}`")
            save_session_state(state)
        append_event(
            LogEvent(
                id=generate_event_id(),
                timestamp=utc_now_iso(),
                session_id=get_session_id(payload),
                event_type="validation",
                actor="agent",
                summary=f"Validated via shell: {truncate_text(command, 80)}",
                details={
                    "method": "automated test/lint",
                    "description": command,
                    "outcome": outcome,
                },
            )
        )

    if exit_code not in (0, None) and not is_validation:
        append_event(
            LogEvent(
                id=generate_event_id(),
                timestamp=utc_now_iso(),
                session_id=get_session_id(payload),
                event_type="ai_bug",
                actor="agent",
                summary=f"Shell command failed: {truncate_text(command, 80)}",
                details={
                    "issue": f"Command `{command}` exited with code {exit_code}",
                    "source": "shell",
                },
            )
        )

    return LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=get_session_id(payload),
        event_type="shell",
        actor="agent",
        summary=f"Ran shell command: {truncate_text(command, 80)}",
        details={
            "command": truncate_text(command, 200),
            "exit_code": exit_code,
            "is_validation": is_validation,
        },
    )


def build_lint_event(payload: dict[str, Any], tool_input: dict[str, Any]) -> LogEvent:
    paths = tool_input.get("paths") or tool_input.get("path") or "project files"
    append_event(
        LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id=get_session_id(payload),
            event_type="validation",
            actor="agent",
            summary="Validated code with linter",
            details={
                "method": "linter",
                "description": f"ReadLints on {paths}",
                "outcome": "completed",
            },
        )
    )
    return LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=get_session_id(payload),
        event_type="tool",
        actor="agent",
        summary="Invoked ReadLints",
        details={"tool": "ReadLints", "paths": paths},
    )


def build_task_event(payload: dict[str, Any], tool_input: dict[str, Any]) -> LogEvent:
    description = str(tool_input.get("description") or tool_input.get("prompt") or "explore the codebase")
    subagent_type = str(tool_input.get("subagent_type") or tool_input.get("subagentType") or "explore")
    return LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=get_session_id(payload),
        event_type="task",
        actor="agent",
        summary=f"Started subagent task: {truncate_text(description, 80)}",
        details={"subagent_type": subagent_type, "description": truncate_text(description, 200)},
    )


def build_mcp_event(payload: dict[str, Any], tool: str, tool_input: dict[str, Any]) -> LogEvent:
    server = str(tool_input.get("server") or "unknown")
    tool_name = str(tool_input.get("toolName") or tool_input.get("tool_name") or tool)
    return LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=get_session_id(payload),
        event_type="mcp",
        actor="agent",
        summary=f"MCP call: {server}/{tool_name}",
        details={"server": server, "tool_name": tool_name},
    )


def build_tool_use_event(payload: dict[str, Any]) -> LogEvent | None:
    tool = get_tool_name(payload)
    if not tool:
        return None
    tool_input = get_tool_input(payload)

    if tool in SEARCH_TOOLS:
        return build_search_event(payload, tool, tool_input)
    if tool in READ_TOOLS:
        return build_read_event(payload, tool_input)
    if tool in EDIT_TOOLS:
        return build_edit_event(payload, tool, tool_input)
    if tool in SHELL_TOOLS:
        return build_shell_event(payload, tool_input)
    if tool in LINT_TOOLS:
        return build_lint_event(payload, tool_input)
    if tool in TASK_TOOLS:
        return build_task_event(payload, tool_input)
    if tool.startswith("MCP:") or "mcp" in tool.lower():
        return build_mcp_event(payload, tool, tool_input)

    return LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=get_session_id(payload),
        event_type="tool",
        actor="agent",
        summary=f"Tool call: {tool}",
        details={"tool": tool},
    )


def handle_session_start(payload: dict[str, Any]) -> None:
    session_id = get_session_id(payload)
    save_session_state({"session_id": session_id, "started_at": utc_now_iso(), "pending_edits": []})
    append_event(
        LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id=session_id,
            event_type="session_start",
            actor="agent",
            summary="AI engineering session started",
            details={"project_root": str(PROJECT_ROOT)},
        )
    )


def handle_prompt(payload: dict[str, Any]) -> None:
    message = truncate_text(redact_secrets(extract_prompt_text(payload)))
    if not message:
        return

    state = load_session_state()
    state["session_id"] = get_session_id(payload) or state.get("session_id", "unknown")

    is_rejection = bool(REJECTION_PROMPT.search(message))
    is_bug = bool(BUG_PROMPT.search(message))
    is_validation = bool(VALIDATION_PROMPT.search(message))

    if is_rejection and state.get("pending_edits"):
        _resolve_pending_edits(state, "rejected", message)
    elif is_bug:
        append_event(
            LogEvent(
                id=generate_event_id(),
                timestamp=utc_now_iso(),
                session_id=state.get("session_id", "unknown"),
                event_type="ai_bug",
                actor="user",
                summary=f"User reported issue: {truncate_text(message, 80)}",
                details={"issue": message, "source": "user prompt"},
            )
        )
    elif is_validation:
        append_event(
            LogEvent(
                id=generate_event_id(),
                timestamp=utc_now_iso(),
                session_id=state.get("session_id", "unknown"),
                event_type="validation",
                actor="user",
                summary=f"Validation requested: {truncate_text(message, 80)}",
                details={"method": "manual review", "description": message, "outcome": "requested"},
            )
        )

    append_event(
        LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id=state.get("session_id", "unknown"),
            event_type="prompt",
            actor="user",
            summary=f"User prompt: {truncate_text(message, 80)}",
            details={
                "message": message,
                "is_validation_request": is_validation,
                "is_rejection": is_rejection,
                "is_bug_report": is_bug,
            },
        )
    )
    save_session_state(state)


def handle_tool_use(payload: dict[str, Any]) -> None:
    event = build_tool_use_event(payload)
    if event and event.event_type not in {"validation"}:
        append_event(event)
    elif event and event.event_type == "tool" and event.details.get("tool") == "ReadLints":
        append_event(event)


def handle_tool_failure(payload: dict[str, Any]) -> None:
    tool = get_tool_name(payload)
    error = extract_error_text(payload)
    append_event(
        LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id=get_session_id(payload),
            event_type="tool_failure",
            actor="agent",
            summary=f"Tool failure: {tool}",
            details={"tool": tool, "error": error},
        )
    )
    append_event(
        LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id=get_session_id(payload),
            event_type="ai_bug",
            actor="agent",
            summary=f"AI tool failure: {tool}",
            details={"issue": error, "source": f"tool failure ({tool})"},
        )
    )


def handle_response(payload: dict[str, Any]) -> None:
    summary = truncate_text(redact_secrets(extract_response_text(payload)), 200)
    if not summary:
        return
    append_event(
        LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id=get_session_id(payload),
            event_type="response",
            actor="agent",
            summary=f"Agent response: {truncate_text(summary, 80)}",
            details={"summary": summary},
        )
    )


def handle_session_end(payload: dict[str, Any]) -> None:
    state = load_session_state()
    if state.get("pending_edits"):
        _accept_pending_edits(state)

    duration_seconds = None
    if state.get("started_at"):
        try:
            start = datetime.fromisoformat(str(state["started_at"]).replace("Z", "+00:00"))
            duration_seconds = int((datetime.now(timezone.utc) - start).total_seconds())
        except ValueError:
            pass

    append_event(
        LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id=get_session_id(payload) or state.get("session_id", "unknown"),
            event_type="session_end",
            actor="agent",
            summary="AI engineering session ended",
            details={"duration_seconds": duration_seconds},
        )
    )
    save_session_state({})


def handle_bug_resolution(payload: dict[str, Any]) -> None:
    """Manual or hook-triggered bug resolution logging."""
    issue = payload.get("issue") or payload.get("prompt") or "Unknown issue"
    resolution = payload.get("resolution") or payload.get("message") or "Resolved"
    append_event(
        LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id=get_session_id(payload),
            event_type="bug_resolution",
            actor="agent",
            summary=f"Bug resolved: {truncate_text(str(issue), 80)}",
            details={"issue": issue, "resolution": resolution},
        )
    )


HANDLERS = {
    "session_start": handle_session_start,
    "prompt": handle_prompt,
    "tool_use": handle_tool_use,
    "tool_failure": handle_tool_failure,
    "response": handle_response,
    "session_end": handle_session_end,
    "bug_resolution": handle_bug_resolution,
}


def main() -> int:
    if len(sys.argv) < 2:
        return 0
    handler = HANDLERS.get(sys.argv[1])
    if not handler:
        return 0
    try:
        handler(read_stdin_json())
    except Exception:
        traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
