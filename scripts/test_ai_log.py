#!/usr/bin/env python3
"""Manual test for AI Engineering Log — simulates Cursor Python hook payloads."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSONL = ROOT / "logs" / "ai-engineering-log.jsonl"
WRITER = ROOT / ".cursor" / "hooks" / "log_writer.py"
PYTHON = sys.executable


def count_lines() -> int:
    if not JSONL.exists():
        return 0
    return len([line for line in JSONL.read_text(encoding="utf-8").splitlines() if line.strip()])


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
    before = count_lines()
    print(f"Events before test: {before}")

    tests = [
        (
            "prompt",
            {
                "conversation_id": "manual-test",
                "prompt": (
                    "Help me create a plan to implement a new feature: AI Engineering Log "
                    "that documents pair programming with enterprise standards."
                ),
            },
        ),
        (
            "tool_use",
            {
                "conversation_id": "manual-test",
                "tool_name": "Grep",
                "tool_input": {"pattern": "engineering log", "path": str(ROOT)},
                "tool_output": "",
            },
        ),
        (
            "tool_use",
            {
                "conversation_id": "manual-test",
                "tool_name": "Write",
                "tool_input": {"path": ".cursor/hooks/log_writer.py"},
            },
        ),
        (
            "tool_use",
            {
                "conversation_id": "manual-test",
                "tool_name": "Shell",
                "tool_input": {"command": "py -3.14 scripts/regenerate_log_summary.py"},
                "tool_output": {"exit_code": 0},
            },
        ),
    ]

    for command, payload in tests:
        run_hook(command, payload)
        print(f"  + logged: {command} ({payload.get('tool_name') or payload.get('prompt', '')[:40]})")

    after = count_lines()
    print(f"Events after test:  {after}")
    print(f"New entries:        {after - before}")
    print("\nOpen AI_ENGINEERING_LOG.md to review the narrative log.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
