# pulse-guard-decision-automation-platform

PulseGuard is an enterprise Decision Automation Platform enabling configurable rules, workflow orchestration, policy management, explainable AI-assisted decisions, audit history, versioning, and cloud-native scalability.

## AI Engineering Log

This project maintains a structured **AI Engineering Log** documenting how Cursor AI was used as a **Pair Programming** partner under **Enterprise Engineering Standards**.

### Log file

| File | Purpose |
|------|---------|
| [`AI_ENGINEERING_LOG.md`](AI_ENGINEERING_LOG.md) | Human-readable log with six audit categories |
| [`logs/ai-engineering-log.jsonl`](logs/ai-engineering-log.jsonl) | Structured source of truth |

### Six log categories

| Section | What is captured |
|---------|------------------|
| **AI Tools Used** | Grep, Write, Shell, Task, MCP, ReadLints, etc. |
| **Key Prompts Provided** | Every user prompt with timestamp |
| **AI-Generated Code Accepted** | Files AI wrote that were kept (validated or session-end acceptance) |
| **AI-Generated Code Rejected or Modified** | Prompts like "no, use Python instead" or AI re-edits same file |
| **How AI Outputs Were Validated** | Test runs, lint checks, manual "verify/test" prompts |
| **Bugs & Resolutions** | Shell failures, tool errors, user bug reports + fixes |

### How it works

Python Cursor hooks in [`.cursor/hooks.json`](.cursor/hooks.json) call [`.cursor/hooks/log_writer.py`](.cursor/hooks/log_writer.py) on every AI action.

**Requirements:** Python 3.14+ (`py -3.14` on Windows).

### Manual entries

Log rejections, validations, or bug resolutions manually:

```bash
py -3.14 scripts/log_manual_entry.py rejected --file ".cursor/hooks/log_writer.mjs" --reason "Switched to Python hooks"
py -3.14 scripts/log_manual_entry.py validation --reason "Reviewed AI_ENGINEERING_LOG.md format manually"
py -3.14 scripts/log_manual_entry.py resolution --reason "Wrong section titles" --resolution "Fixed prompt keyword priority"
```

### Test & rebuild

```bash
py -3.14 scripts/test_ai_log.py
py -3.14 scripts/regenerate_log_summary.py
```

Restart Cursor after cloning if hooks do not load immediately.
