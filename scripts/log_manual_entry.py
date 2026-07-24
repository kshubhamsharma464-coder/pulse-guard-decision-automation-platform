#!/usr/bin/env python3
"""Manually log rejections, bug resolutions, or validations into the AI Engineering Log."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".cursor" / "hooks"))

from log_event import LogEvent, append_event, generate_event_id, utc_now_iso  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Manually add entries to the AI Engineering Log")
    parser.add_argument(
        "type",
        choices=["rejected", "modified", "accepted", "validation", "bug", "resolution"],
        help="Entry type",
    )
    parser.add_argument("--file", help="File path (for code entries)")
    parser.add_argument("--reason", required=True, help="Reason, issue, or description")
    parser.add_argument("--resolution", help="How the bug was resolved")
    parser.add_argument("--method", default="manual review", help="Validation method")
    args = parser.parse_args()

    if args.type == "rejected":
        event = LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id="manual",
            event_type="code_rejection",
            actor="user",
            summary=f"Manually rejected: {args.file or 'code'}",
            details={"file_path": args.file or "unknown", "reason": args.reason, "code_status": "rejected"},
        )
    elif args.type == "modified":
        event = LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id="manual",
            event_type="edit",
            actor="user",
            summary=f"Manually marked modified: {args.file or 'code'}",
            details={
                "file_path": args.file or "unknown",
                "modification_reason": args.reason,
                "code_status": "modified",
            },
        )
    elif args.type == "accepted":
        event = LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id="manual",
            event_type="edit",
            actor="user",
            summary=f"Manually accepted: {args.file or 'code'}",
            details={
                "file_path": args.file or "unknown",
                "code_status": "accepted",
                "validation": args.reason,
            },
        )
    elif args.type == "validation":
        event = LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id="manual",
            event_type="validation",
            actor="user",
            summary=f"Manual validation: {args.reason[:80]}",
            details={"method": args.method, "description": args.reason, "outcome": "passed"},
        )
    elif args.type == "bug":
        event = LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id="manual",
            event_type="ai_bug",
            actor="user",
            summary=f"Bug reported: {args.reason[:80]}",
            details={"issue": args.reason, "source": "manual", "resolution": args.resolution},
        )
    else:
        event = LogEvent(
            id=generate_event_id(),
            timestamp=utc_now_iso(),
            session_id="manual",
            event_type="bug_resolution",
            actor="user",
            summary=f"Bug resolved: {args.reason[:80]}",
            details={"issue": args.reason, "resolution": args.resolution or "Fixed"},
        )

    append_event(event)
    print(json.dumps({"status": "logged", "type": args.type, "id": event.id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
