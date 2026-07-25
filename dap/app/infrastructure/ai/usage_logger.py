"""Append-only structured log of AI-assisted work on this project, written to
docs/ai-usage-log.md in the "### Entry #N" template the team standardized on
(see that file's header for the field definitions).

Two entry points:

- `log_ai_call` + `wrap_provider_with_logging`: wraps a live AIProvider
  instance's generate_rule/document_rule/explain_decision methods so every
  real call made through the running app is logged automatically. Opt-in via
  Settings.ai_usage_log_enabled (default False) so importing this module
  never writes to the repo, and never affects a test run, unless explicitly
  turned on.
- `log_ai_entry()`: a manual helper for logging AI-assisted coding sessions
  (e.g. a Claude Code session that wrote or modified a module) that never go
  through the AIProvider interface at runtime -- this is how the seed
  entries in docs/ai-usage-log.md were produced.

A logging failure never breaks the caller -- this is an audit trail, not a
control path, so `log_ai_call` swallows (and only warns on) its own errors
without touching the wrapped call's result or exception.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# app/infrastructure/ai/usage_logger.py -> parents[3] is the project root (dap/)
DEFAULT_LOG_PATH = Path(__file__).resolve().parents[3] / "docs" / "ai-usage-log.md"

_ENTRY_HEADER_RE = re.compile(r"^### Entry #(\d+)", re.MULTILINE)

_LOG_HEADER = (
    "# AI Usage Log\n\n"
    "Structured, per-interaction record of AI-assisted work on this "
    "project. Entries are appended automatically by "
    "`app/infrastructure/ai/usage_logger.py`.\n\n---\n\n"
)


def _next_entry_number(path: Path) -> int:
    if not path.exists():
        return 1
    numbers = [int(m) for m in _ENTRY_HEADER_RE.findall(path.read_text(encoding="utf-8"))]
    return max(numbers, default=0) + 1


def _format_entry(
    number: int,
    title: str,
    ai_tool: str,
    task_module: str,
    prompt: str,
    output_summary: str,
    decision: str,
    modified_reason: str,
    validation: str,
    bugs_found: str,
    author: str,
    timestamp: str,
) -> str:
    prompt_lines = prompt.strip().splitlines() or [""]
    quoted_prompt = "\n".join(f"  > {line}" if line else "  >" for line in prompt_lines)
    return (
        f"### Entry #{number} — {title}\n"
        f"- *Timestamp / author:* {timestamp} — {author}\n"
        f"- *AI tool + model:* {ai_tool}\n"
        f"- *Task / module:* {task_module}\n"
        f"- *Prompt (verbatim):*\n"
        f"{quoted_prompt}\n"
        f"- *AI output summary:* {output_summary}\n"
        f"- *Decision:* {decision}\n"
        f"- *If modified/rejected, why:* {modified_reason or 'n/a'}\n"
        f"- *How it was validated:* {validation}\n"
        f"- *Bugs found (if any) and resolution:* {bugs_found}\n"
    )


class AIUsageLogger:
    """Thread-safe appender for docs/ai-usage-log.md."""

    def __init__(self, path: Path = DEFAULT_LOG_PATH):
        self.path = path
        self._lock = threading.Lock()

    def log_entry(
        self,
        *,
        title: str,
        ai_tool: str,
        task_module: str,
        prompt: str,
        output_summary: str,
        decision: str = "Accepted as-is",
        modified_reason: str = "",
        validation: str = "Not yet validated.",
        bugs_found: str = "None reported.",
        author: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> int:
        """Format and append one entry. Returns the assigned entry number."""
        author = author or os.environ.get("AI_LOG_AUTHOR", "unknown")
        timestamp = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                self.path.write_text(_LOG_HEADER, encoding="utf-8")

            number = _next_entry_number(self.path)
            entry = _format_entry(
                number, title, ai_tool, task_module, prompt, output_summary,
                decision, modified_reason, validation, bugs_found, author, timestamp,
            )
            with self.path.open("a", encoding="utf-8") as f:
                f.write(entry + "\n---\n\n")
            return number


_default_logger = AIUsageLogger()


def log_ai_entry(
    title: str,
    ai_tool: str,
    task_module: str,
    prompt: str,
    output_summary: str,
    decision: str = "Accepted as-is",
    modified_reason: str = "",
    validation: str = "Not yet validated.",
    bugs_found: str = "None reported.",
    author: Optional[str] = None,
    timestamp: Optional[str] = None,
    logger_instance: Optional[AIUsageLogger] = None,
) -> int:
    """Manual entry point -- call this after an AI-assisted coding session
    (e.g. Claude Code writing or modifying a module) that never goes through
    the AIProvider interface at runtime. Returns the assigned entry number."""
    target = logger_instance or _default_logger
    return target.log_entry(
        title=title, ai_tool=ai_tool, task_module=task_module, prompt=prompt,
        output_summary=output_summary, decision=decision,
        modified_reason=modified_reason, validation=validation,
        bugs_found=bugs_found, author=author, timestamp=timestamp,
    )


def _truncate(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# method name -> (entry title, name of the argument holding the "prompt")
_METHOD_META = {
    "generate_rule": ("AI rule generation", "description"),
    "document_rule": ("AI rule documentation", "rule"),
    "explain_decision": ("AI decision explanation", "decision_facts"),
}


def log_ai_call(method_name: str, ai_tool_label: Callable[[], str]) -> Callable:
    """Decorator for an AIProvider bound method: after a real call completes,
    logs the method's primary input argument as the "prompt" and a truncated
    summary of the result. Never suppresses the wrapped call's own exception;
    a failure in logging itself is only warned about, never raised."""
    title, prompt_arg = _METHOD_META[method_name]

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            prompt_value = kwargs.get(prompt_arg, args[0] if args else "")
            result = func(self, *args, **kwargs)
            try:
                _default_logger.log_entry(
                    title=title,
                    ai_tool=ai_tool_label(),
                    task_module=(
                        f"app.infrastructure.ai (live call via "
                        f"{type(self).__name__}.{method_name})"
                    ),
                    prompt=_truncate(prompt_value, 1000),
                    output_summary=_truncate(result, 500),
                    decision="Accepted as-is",
                    validation=(
                        "Runtime call -- output returned to the caller for human "
                        "review per this project's AI safety model (see "
                        "docs/ai-assist.md); not independently validated by the logger."
                    ),
                    bugs_found="None reported.",
                    author=os.environ.get("AI_LOG_AUTHOR", "system"),
                )
            except Exception:
                logger.warning(
                    "AI usage logging failed for %s.%s",
                    type(self).__name__, method_name, exc_info=True,
                )
            return result

        return wrapper

    return decorator


def wrap_provider_with_logging(provider: Any, settings: Any) -> Any:
    """Return `provider` with generate_rule/document_rule/explain_decision
    wrapped for automatic logging if settings.ai_usage_log_enabled is True;
    otherwise return it untouched. Called once, from
    app/infrastructure/ai/factory.py::create_ai_provider -- so every entry
    point (API router, jobs, anything constructed through the factory) gets
    logging for free, regardless of which concrete provider is configured."""
    if not getattr(settings, "ai_usage_log_enabled", False):
        return provider

    def ai_tool_label() -> str:
        return f"{type(provider).__name__} (provider={settings.ai_provider}, model={settings.ai_model})"

    for method_name in _METHOD_META:
        bound = getattr(provider, method_name)
        decorated = log_ai_call(method_name, ai_tool_label)(bound.__func__)
        setattr(provider, method_name, decorated.__get__(provider, type(provider)))

    return provider
