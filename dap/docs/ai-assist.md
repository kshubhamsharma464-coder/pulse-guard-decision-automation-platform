# AI-Assisted Rule Authoring -- Phase 3

Natural-language rule drafting, AI-generated rule documentation, and
AI-narrated decision explanations -- all strictly non-authoritative. AI
never creates, publishes, activates, or alters a rule or a decision; every
AI output either requires an explicit human (or separately-permissioned)
action to take effect, or is read-only prose layered on top of an
already-final, deterministic result.

## The safety boundary, concretely

This isn't just a policy statement -- it's structural:

- **`generate_rule()`** returns a plain dict shaped like `CreateRuleRequest`.
  `GenerateRuleFromDescriptionUseCase` never touches
  `RulePackRepository` -- there is no code path from "AI drafted a rule"
  to "a rule exists in the system" without a caller explicitly calling
  `POST /api/v1/rules` themselves, and from there the normal
  Draft -> Published -> Active lifecycle (`docs/rule-management.md`,
  gated by `rules:publish`/`rules:activate`, a *different* permission
  than the `rules:edit` this endpoint requires) still applies in full.
  `tests/test_ai_api.py::test_generate_rule_returns_draft_without_persisting_anything`
  asserts the rule-pack repository's contents are byte-identical before
  and after a generate-rule call.
- **`explain_decision()`** runs strictly after `EvaluateIncidentUseCase`
  has already produced and persisted a `Decision`. It reads a plain-fact
  snapshot of that decision and returns prose -- it has no reference to
  the repositories or use cases that could change one.
  `Decision.explanation` (the deterministic explanation
  `ExplainabilityBuilder` always produces, zero AI involvement) is
  returned alongside the AI narration in every response, never replaced
  by it.
- **`document_rule()`** is read-only prose about an existing or draft rule
  payload -- it has no write path at all.

## Provider abstraction (Strategy + Factory patterns)

`app/domain/interfaces/ai_provider.py` defines `AIProvider` (three
methods: `generate_rule`, `document_rule`, `explain_decision`).
`app/infrastructure/ai/factory.py`'s `create_ai_provider(settings)` is the
only place that branches on `Settings.ai_provider`:

| `AI_PROVIDER` | Implementation | Notes |
|---|---|---|
| `stub` (default) | `StubAIProvider` | Deterministic, keyword/regex-based extraction (field name + threshold + action keywords). No network. Works everywhere, including this project's own test suite. |
| `openai_compatible` | `OpenAICompatibleProvider` | Plain `httpx` POST to `{AI_BASE_URL}/chat/completions` -- works against a local Ollama/llama.cpp server (the default `AI_BASE_URL`) or real OpenAI/Azure OpenAI by changing `AI_BASE_URL`/`AI_API_KEY` only. |
| `gemini_compatible` | `GeminiCompatibleProvider` | Google's Gemini REST shape (`contents`/`parts`/`candidates`) -- genuinely different wire format from OpenAI's, hence a separate implementation rather than an if-branch. |

Adding a fourth provider (e.g. a real OpenAI SDK client, Anthropic, a
fine-tuned in-house model) means writing one new class implementing
`AIProvider` and adding one branch to the factory -- every use case and
the router are already written against the interface and need zero
changes (the Strategy pattern's actual point, not just a description of
it).

## Prompts

`app/infrastructure/ai/prompts.py` is the single source of truth for
every system/user prompt the two LLM-backed providers send --
`RULE_GENERATION_SYSTEM_PROMPT` (specifies the exact JSON shape expected
back, the supported condition operators, and an explicit instruction to
flag rather than fabricate when the description is too vague),
`RULE_DOCUMENTATION_SYSTEM_PROMPT`, and `DECISION_EXPLANATION_SYSTEM_PROMPT`
(explicitly tells the model it is narrating an already-final decision,
not making one). See `docs/AI_ENGINEERING_LOG.md` for why these were
worded the way they are.

## Failure handling

Any network error, timeout, non-2xx response, or unparseable/unexpected
response shape from an LLM-backed provider raises `AIProviderError`
(`app/infrastructure/ai/common.py`), which the router
(`app/interfaces/api/ai_router.py`) turns into `502 Bad Gateway`. Nothing
falls back to fabricating a plausible-looking result on failure -- the
entire value of "AI-assisted" is that a human reviews *real* output, so a
silently-degraded fake success would be worse than an honest error.

`OpenAICompatibleProvider`/`GeminiCompatibleProvider` both accept an
optional `transport` constructor argument (an `httpx.BaseTransport`) --
`None` in every real deployment (httpx's real network transport);
`tests/test_ai_providers.py` injects an `httpx.MockTransport` so the real
prompt-building/HTTP-call/response-parsing/error-handling code runs
end-to-end against a scripted fake server in tests, rather than mocking
the provider's methods themselves (which would only prove the router
calls a method, not that the provider works).

## REST API (tag "AI")

- **`POST /api/v1/ai/generate-rule`** -- `{description, family?, region?,
  samplePayload?}` -> `{rule, isValid, validationErrors, aiProvider}`.
  Requires `rules:edit` (same permission as manually authoring a rule).
  The returned `rule` is run through the exact same `ValidateRuleUseCase`
  a human-authored rule would be (`docs/rule-management.md`) -- invalid
  drafts are still returned, with their errors, rather than rejected
  outright, since hiding *why* it's invalid would defeat the point of
  human review.
- **`POST /api/v1/ai/document-rule`** -- `{ruleId}` or `{rule}` (inline
  payload) -> `{documentation, aiProvider}`. Requires `rules:read`.
- **`POST /api/v1/ai/explain-decision/{incident_id}`** -> `{incidentId,
  deterministicExplanation, aiExplanation, aiProvider}`. Requires
  `decisions:read`. `404` if no decision exists yet for that incident.

Every endpoint is inert (open to anonymous callers) unless
`AUTH_REQUIRED=true`, same backward-compatibility contract as every other
endpoint added since Phase 2 (`docs/auth.md`).

## Running it

Zero setup with the default stub provider. To point at a local Llama
server via Ollama:

```bash
ollama pull llama3
ollama serve   # exposes an OpenAI-compatible endpoint at :11434/v1 by default
```

then in `.env`: `AI_PROVIDER=openai_compatible` (the default `AI_BASE_URL`
already points at Ollama's default port). Swapping to real OpenAI later:
`AI_BASE_URL=https://api.openai.com/v1`, `AI_API_KEY=<real key>`,
`AI_MODEL=gpt-4o-mini` (or similar) -- no code changes, no restart of
anything but the process picking up the new `.env`.

## Not included in this phase (flagged, not silently skipped)

- **Test generation assist** -- the original spec mentions AI-assisted
  test generation as a possible feature; not built here. `generate-rule`
  and `document-rule` were prioritized as the two concretely spec'd
  endpoints (`POST /api/v1/ai/generate-rule`,
  `POST /api/v1/ai/document-rule`); `explain-decision` was added as the
  third AI requirement explicitly named in the original brief
  ("decision explanation assist").
- **No real OpenAI/Gemini credentials were available in this environment**
  to test `OpenAICompatibleProvider`/`GeminiCompatibleProvider` against a
  live endpoint -- verified via `httpx.MockTransport` instead (see
  "Failure handling" above). Flagged honestly, same as Phase 1's Postgres
  migration verification.
- **No streaming responses** -- every AI call is a single synchronous
  request/response; fine for the short outputs these three endpoints
  produce (a rule JSON, a few sentences), not built for a chat-style
  interface.

## Verification performed

- Full regression: 175 passed (148 pre-existing + 16 new AI-provider unit
  tests + 11 new AI-router HTTP tests), zero changes to any pre-existing
  test file.
- `tests/test_ai_providers.py`: factory provider selection; `StubAIProvider`
  field/threshold/action extraction and its conservative fallback when a
  description can't be parsed; `OpenAICompatibleProvider`/
  `GeminiCompatibleProvider` against `httpx.MockTransport` -- JSON
  parsing (including markdown-fence stripping), HTTP-error handling,
  unexpected-response-shape handling.
- `tests/test_ai_api.py`: generate-rule's structural no-side-effects
  guarantee (rule-pack repository contents asserted unchanged before/
  after); AI-provider-error surfacing as 502 (via a fault-injected
  provider); document-rule by id and by inline payload; explain-decision
  returning both the deterministic and AI explanations, and 404 when no
  decision exists; RBAC (editor can generate/document but not
  explain-decision, which needs `decisions:read`; viewer cannot
  generate-rule).
