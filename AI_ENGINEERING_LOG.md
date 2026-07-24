# AI Engineering Log

## Overview
This log documents how Generative AI (Cursor IDE / Claude / GPT) was leveraged as a true **Pair Programming** partner throughout the development of **PulseGuard**.

Rather than using AI to generate a single-file prototype, AI was strictly instructed to adhere to **Enterprise Engineering Standards** (Clean Architecture, SOLID principles, and comprehensive test coverage).

> Auto-generated from `logs/ai-engineering-log.jsonl` via Python Cursor hooks. Last updated: 2026-07-24 10:27:20 UTC

---

## AI Tools Used

- **Write** — 2 uses
- **Shell** — 2 uses
- **Grep** — 1 use

---

## Key Prompts Provided

1. *2026-07-24 10:27 UTC* — "Help me implement AI Engineering Log with Python hooks and enterprise standards."
2. *2026-07-24 10:27 UTC* — "No, use Python hooks instead of Node.js for the log writer."
3. *2026-07-24 10:27 UTC* — "There is a bug — section titles are wrong. Fix the inference logic."

---

## AI-Generated Code Accepted

- `.cursor/hooks/log_writer.py` — accepted via **Write** (2026-07-24 10:27 UTC)
  - Validated by: `py -3.14 scripts/test_ai_log.py`

---

## AI-Generated Code Rejected or Modified

- `.cursor/hooks/log_writer.mjs` — **Rejected** (2026-07-24 10:27 UTC)
  - **Reason:** No, use Python hooks instead of Node.js for the log writer.

---

## How AI Outputs Were Validated

- *2026-07-24 10:27 UTC* — **automated test/lint**: py -3.14 scripts/test_ai_log.py → _passed_

---

## Bugs or Issues Introduced by AI & Resolutions

- *2026-07-24 10:27 UTC* — **Issue** (user prompt): There is a bug — section titles are wrong. Fix the inference logic.
- *2026-07-24 10:27 UTC* — **Issue:** Section titles used shell keywords instead of prompt keywords
  - **Resolution:** Updated _infer_section_title to prioritize prompt text

---

## Summary

The AI was used to multiply the output of a Principal Engineer — not to produce throwaway prototypes. This log tracks every tool invocation, key prompt, code acceptance decision, validation step, and bug resolution to maintain full transparency over AI-assisted development.
