#!/usr/bin/env python3
"""Manual test for AI Engineering Log — simulates all six log categories."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSONL = ROOT / "logs" / "ai-engineering-log.jsonl"
WRITER = ROOT / ".cursor" / "hooks" / "log_writer.py"
PYTHON = sys.executable


def run_hook(command: str, payload: dict) -> None:
    subprocess.run(
        [PYTHON, str(WRITER), command],
        input=json.dumps(payload),
        cwd=ROOT,
        text=True,
        check=True,
        capture_output=True,
    )


def main() -> int:
    if JSONL.exists():
        JSONL.unlink()

    tests = [
        ("session_start", {"conversation_id": "demo-session"}),
        (
            "prompt",
            {
                "conversation_id": "demo-session",
                "prompt": "Help me implement AI Engineering Log with Python hooks and enterprise standards.",
            },
        ),
        (
            "tool_use",
            {
                "conversation_id": "demo-session",
                "tool_name": "Grep",
                "tool_input": {"pattern": "engineering log", "path": str(ROOT)},
                "tool_output": "",
            },
        ),
        (
            "tool_use",
            {
                "conversation_id": "demo-session",
                "tool_name": "Write",
                "tool_input": {"path": ".cursor/hooks/log_writer.mjs", "contents": "// node version"},
            },
        ),
        (
            "prompt",
            {
                "conversation_id": "demo-session",
                "prompt": "No, use Python hooks instead of Node.js for the log writer.",
            },
        ),
        (
            "tool_use",
            {
                "conversation_id": "demo-session",
                "tool_name": "Write",
                "tool_input": {"path": ".cursor/hooks/log_writer.py", "contents": "# python version"},
            },
        ),
        (
            "tool_use",
            {
                "conversation_id": "demo-session",
                "tool_name": "Shell",
                "tool_input": {"command": "py -3.14 scripts/test_ai_log.py"},
                "tool_output": {"exit_code": 0},
            },
        ),
        (
            "prompt",
            {
                "conversation_id": "demo-session",
                "prompt": "There is a bug — section titles are wrong. Fix the inference logic.",
            },
        ),
        ("session_end", {"conversation_id": "demo-session"}),
    ]

    for command, payload in tests:
        run_hook(command, payload)
        print(f"  + {command}")

    subprocess.run([PYTHON, str(ROOT / "scripts" / "log_manual_entry.py"), "resolution",
                      "--reason", "Section titles used shell keywords instead of prompt keywords",
                      "--resolution", "Updated _infer_section_title to prioritize prompt text"], check=True)
    print("\nDemo log generated. Open AI_ENGINEERING_LOG.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
