#!/usr/bin/env python3
"""Rebuild AI_ENGINEERING_LOG.md from logs/ai-engineering-log.jsonl."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".cursor" / "hooks"))

from log_event import generate_markdown_summary  # noqa: E402


def main() -> int:
    generate_markdown_summary()
    print("Regenerated AI_ENGINEERING_LOG.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
