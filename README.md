# pulse-guard-decision-automation-platform

PulseGuard is an enterprise Decision Automation Platform enabling configurable rules, workflow orchestration, policy management, explainable AI-assisted decisions, audit history, versioning, and cloud-native scalability.

## AI Engineering Log

This project maintains a narrative **AI Engineering Log** — documenting how Cursor AI was leveraged as a true **Pair Programming** partner, adhering to **Enterprise Engineering Standards** (Clean Architecture, SOLID principles, and comprehensive test coverage).

### Log files

| File | Purpose |
|------|---------|
| [`AI_ENGINEERING_LOG.md`](AI_ENGINEERING_LOG.md) | Narrative log with Challenge / AI Intervention sections (like a hackathon engineering diary) |
| [`logs/ai-engineering-log.jsonl`](logs/ai-engineering-log.jsonl) | Structured source of truth (one JSON object per line) |

### How it works

Python Cursor hooks in [`.cursor/hooks.json`](.cursor/hooks.json) call [`.cursor/hooks/log_writer.py`](.cursor/hooks/log_writer.py) after each AI action:

1. Appends a structured event to `logs/ai-engineering-log.jsonl`
2. Regenerates `AI_ENGINEERING_LOG.md` in narrative format

**Requirements:** Python 3.14+ (hooks use `py -3.14` on Windows).

### Example narrative section

```markdown
## 1. AI Engineering Log & Audit Trail

**Challenge**: Help me create a plan to implement a new feature: AI Engineering Log
**AI Intervention**:
- Utilized **Grep** to search the codebase for `engineering log` (0 matches).
- Authored `.cursor/hooks/log_writer.py` adhering to enterprise engineering standards.
- Dynamically shifted to **DevOps mode** — executed `py -3.14 scripts/regenerate_log_summary.py`.
```

### Manual rebuild & test

```bash
py -3.14 scripts/regenerate_log_summary.py
py -3.14 scripts/test_ai_log.py
```

### Notes

- Secrets in shell commands and prompts are redacted before writing.
- Hook failures do not block AI agent work (fail-open design).
- Restart Cursor after cloning if hooks do not load immediately.
