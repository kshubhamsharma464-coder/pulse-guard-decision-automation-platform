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
    LogEvent,
    PROJECT_ROOT,
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
    raw = sys.stdin.read()
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
    return str(get_nested(payload, "tool", "name", default="") or "")


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


def count_grep_matches(output: Any) -> int | None:
    if output is None:
        return None
    text = output if isinstance(output, str) else json.dumps(output)
    if not text:
        return 0
    if "No matches found" in text or text.strip() == "":
        return 0
    return len(re.findall(r"^[^\n]+:\d+:", text, flags=re.MULTILINE)) or None


def build_search_event(payload: dict[str, Any], tool: str, tool_input: dict[str, Any]) -> LogEvent:
    session_id = get_session_id(payload)
    output = get_tool_output(payload)

    if tool == "WebSearch":
        query = str(tool_input.get("search_term") or tool_input.get("query") or "")
        summary = f"Web search for '{truncate_text(query, 80)}'"
        details = {"tool": tool, "query": query}
    elif tool == "Glob":
        pattern = str(tool_input.get("glob_pattern") or tool_input.get("pattern") or "")
        path = str(tool_input.get("target_directory") or tool_input.get("path") or ".")
        match_count = None
        if isinstance(output, str):
            match_count = len([line for line in output.splitlines() if line.strip()])
        summary = f"Searched files matching '{truncate_text(pattern, 80)}'"
        details = {"tool": tool, "query": pattern, "path": path, "match_count": match_count}
    else:
        query = str(tool_input.get("pattern") or tool_input.get("query") or "")
        path = str(tool_input.get("path") or ".")
        match_count = count_grep_matches(output)
        summary = f"Searched codebase for '{truncate_text(query, 80)}'"
        details = {"tool": tool, "query": query, "path": path, "match_count": match_count}

    return LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=session_id,
        event_type="search",
        actor="agent",
        summary=summary,
        details=details,
    )


def build_read_event(payload: dict[str, Any], tool_input: dict[str, Any]) -> LogEvent:
    file_path = str(tool_input.get("path") or tool_input.get("file_path") or "unknown")
    offset = tool_input.get("offset")
    limit = tool_input.get("limit")
    line_range = None
    if offset is not None or limit is not None:
        line_range = f"{offset or 1}-{limit or 'end'}"

    return LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=get_session_id(payload),
        event_type="read",
        actor="agent",
        summary=f"Read file '{file_path}'",
        details={"file_path": file_path, "line_range": line_range},
    )


def build_edit_event(payload: dict[str, Any], tool: str, tool_input: dict[str, Any]) -> LogEvent:
    file_path = str(tool_input.get("path") or tool_input.get("file_path") or "unknown")
    if tool == "Write":
        operation = "create" if tool_input.get("contents") is not None else "update"
    elif tool == "Delete":
        operation = "delete"
    else:
        operation = "update"

    return LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=get_session_id(payload),
        event_type="edit",
        actor="agent",
        summary=f"{operation.title()} file '{file_path}'",
        details={"file_path": file_path, "operation": operation, "tool": tool},
    )


def build_shell_event(payload: dict[str, Any], tool_input: dict[str, Any]) -> LogEvent:
    command = redact_secrets(str(tool_input.get("command") or ""))
    output = get_tool_output(payload)
    exit_code = None
    if isinstance(output, dict):
        exit_code = output.get("exit_code") or output.get("exitCode")

    return LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=get_session_id(payload),
        event_type="shell",
        actor="agent",
        summary=f"Ran shell command: {truncate_text(command, 80)}",
        details={"command": truncate_text(command, 200), "exit_code": exit_code},
    )


def build_task_event(payload: dict[str, Any], tool_input: dict[str, Any]) -> LogEvent:
    description = str(tool_input.get("description") or tool_input.get("prompt") or "subagent task")
    subagent_type = str(tool_input.get("subagent_type") or tool_input.get("subagentType") or "unknown")

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
    state = {
        "session_id": session_id,
        "started_at": utc_now_iso(),
        "event_count": 0,
    }
    save_session_state(state)

    event = LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=session_id,
        event_type="session_start",
        actor="agent",
        summary="AI engineering session started",
        details={"project_root": str(PROJECT_ROOT)},
    )
    append_event(event)
    state["event_count"] = 1
    save_session_state(state)


def handle_prompt(payload: dict[str, Any]) -> None:
    message = truncate_text(redact_secrets(extract_prompt_text(payload)))
    if not message:
        return

    event = LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=get_session_id(payload),
        event_type="prompt",
        actor="user",
        summary=f"User prompt: {truncate_text(message, 80)}",
        details={"message": message},
    )
    append_event(event)


def handle_tool_use(payload: dict[str, Any]) -> None:
    event = build_tool_use_event(payload)
    if event:
        append_event(event)


def handle_response(payload: dict[str, Any]) -> None:
    summary = truncate_text(redact_secrets(extract_response_text(payload)), 200)
    if not summary:
        return

    event = LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=get_session_id(payload),
        event_type="response",
        actor="agent",
        summary=f"Agent response: {truncate_text(summary, 80)}",
        details={"summary": summary},
    )
    append_event(event)


def handle_session_end(payload: dict[str, Any]) -> None:
    state = load_session_state()
    started_at = state.get("started_at")
    duration_seconds = None
    if started_at:
        try:
            start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
            duration_seconds = int((datetime.now(timezone.utc) - start).total_seconds())
        except ValueError:
            duration_seconds = None

    events = state.get("event_count", 0)
    event = LogEvent(
        id=generate_event_id(),
        timestamp=utc_now_iso(),
        session_id=get_session_id(payload) or state.get("session_id", "unknown"),
        event_type="session_end",
        actor="agent",
        summary="AI engineering session ended",
        details={"duration_seconds": duration_seconds, "total_events": events},
    )
    append_event(event)
    save_session_state({})


HANDLERS = {
    "session_start": handle_session_start,
    "prompt": handle_prompt,
    "tool_use": handle_tool_use,
    "response": handle_response,
    "session_end": handle_session_end,
}


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: log_writer.py <session_start|prompt|tool_use|response|session_end>", file=sys.stderr)
        return 0

    command = sys.argv[1]
    handler = HANDLERS.get(command)
    if not handler:
        print(f"Unknown command: {command}", file=sys.stderr)
        return 0

    try:
        payload = read_stdin_json()
        handler(payload)
    except Exception:
        traceback.print_exc(file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
