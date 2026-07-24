# pulse-guard-decision-automation-platform

PulseGuard is an enterprise Decision Automation Platform enabling configurable rules, workflow orchestration, policy management, explainable AI-assisted decisions, audit history, versioning, and cloud-native scalability.

## AI Engineering Log

This project includes an **AI Engineering Log** that automatically records Cursor AI activity — searches, file reads/edits, shell commands, prompts, and responses.

### Log files

| File | Purpose |
|------|---------|
| [`logs/ai-engineering-log.jsonl`](logs/ai-engineering-log.jsonl) | Structured source of truth (one JSON object per line) |
| [`AI_ENGINEERING_LOG.md`](AI_ENGINEERING_LOG.md) | Auto-generated human-readable summary |

### How it works

Cursor hooks in [`.cursor/hooks.json`](.cursor/hooks.json) call [`.cursor/hooks/log_writer.mjs`](.cursor/hooks/log_writer.mjs) (Node.js) after each AI action. The writer:

1. Appends a structured event to `logs/ai-engineering-log.jsonl`
2. Regenerates `AI_ENGINEERING_LOG.md`

### Example events

When you search the codebase, a log entry like this is created:

```json
{
  "event_type": "search",
  "summary": "Searched codebase for 'engineering log'",
  "details": {
    "tool": "Grep",
    "query": "engineering.?log",
    "path": ".",
    "match_count": 0
  }
}
```

### Manual rebuild

To regenerate the Markdown summary from JSONL:

```bash
node scripts/regenerate_log_summary.mjs
```

### Notes

- Secrets in shell commands and prompts are redacted before writing.
- Hook failures do not block AI agent work (fail-open design).
- Restart Cursor after cloning if hooks do not load immediately.
