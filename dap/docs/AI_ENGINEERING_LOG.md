# AI Engineering Log -- Phase 3

Prompts tried, outputs observed, validation approach, bugs found and
fixed, and lessons carried forward -- for the AI-assisted rule authoring
work in `docs/ai-assist.md`. Written during the implementation session
that built it, not reconstructed after the fact.

## Design decisions and why

**Why a stub provider is the default, not just a fallback.** No live LLM
endpoint (local Ollama, real OpenAI, real Gemini) was reachable in the
sandbox this was built in -- no outbound network access. Rather than
build the LLM-backed providers untested and hope, the priority was: build
`StubAIProvider` first as a real, deterministic implementation of the
same interface, verify the whole system (use cases, router, RBAC,
validation-on-generated-output) against it, *then* build the LLM-backed
providers against the same interface with a transport-injection point so
their internal logic could be tested for real too (see "Testability
retrofit" below). This produced a fully working, fully tested feature
even with zero network access, and the LLM-backed providers slot in
without any other code caring which one is active.

**Why the rule-generation prompt spells out the exact JSON shape,
operator list, and an explicit "don't fabricate" instruction.** Early
draft of the prompt just said "return a JSON rule matching the platform's
schema" -- too vague; a real LLM given that alone would plausibly invent
field names that don't match `CreateRuleRequest` (e.g. `"trigger"`
instead of `"conditions"`, or a `field`/`operator`/`value` leaf shape
instead of the JsonLogic tree this engine actually uses). The final
prompt (`app/infrastructure/ai/prompts.py`) enumerates the exact keys,
gives a concrete example, lists the supported operators
(`app/engine/evaluator_factory.py`'s actual registry), and explicitly
instructs the model to flag an assumption in the `description` field
rather than invent a conditions tree from nothing when the input is too
vague -- mirroring what `StubAIProvider.generate_rule()` does
mechanically (append `"REVIEW AND EDIT..."` to the description on its own
conservative-fallback path). Keeping the stub's fallback behavior and the
LLM prompt's instruction philosophically aligned means a caller sees
similar signal ("this needs human review") regardless of which provider
is configured.

**Why `explain_decision()`'s prompt explicitly says "you are NOT
deciding anything."** The single most important safety property of this
whole phase is that AI never becomes authoritative. Stating that
constraint directly in the system prompt sent to the model -- not just
enforcing it in code -- is a second layer of defense: even if a future
change accidentally fed the AI's explanation output back into something
decision-adjacent, the model was never instructed or expected to produce
decision-shaped output for that call in the first place. The code-level
enforcement (`ExplainDecisionAIUseCase` only reads a `Decision` that
already exists, never writes one) is still the real guarantee; the prompt
wording is defense in depth, not a substitute for it.

## Validation approach

Every `generate_rule()` output -- from any provider -- is run through the
exact same `ValidateRuleUseCase` a human-authored rule submitted via
`POST /api/v1/rules` would be (empty-conditions check, dangling
`conflictsWith` references, malformed condition-tree structure). The
result (`isValid`, `errors`) is returned to the caller alongside the
draft, not swallowed -- an AI-drafted rule that fails validation is still
useful information for the human reviewing it. This is the concrete
implementation of "AI output is validated, not trusted" from the original
brief's AI safety requirement.

## Bugs found and fixed during this build

1. **`httpx.post()` (the module-level convenience function) has no
   `transport` parameter.** First draft of `OpenAICompatibleProvider`/
   `GeminiCompatibleProvider` called `httpx.post(...)` directly, which is
   correct for production but made the providers untestable without a
   live network call -- `httpx.MockTransport` only plugs into
   `httpx.Client(transport=...)`, not the top-level function. Fixed by
   refactoring both providers to construct an `httpx.Client` internally,
   accepting an optional `transport` constructor argument (`None` in
   every real deployment; a `MockTransport` in tests). This is what makes
   `tests/test_ai_providers.py` able to exercise the real HTTP-call/
   JSON-parsing/error-handling code paths end-to-end rather than mocking
   the provider's own methods (which would only prove the router calls a
   method, not that the method works).

2. **`ExplainDecisionAIUseCase` initially imported
   `app.interfaces.api.serializers.decision_to_dict`.** That's an
   application-layer use case depending on the interfaces layer --
   inverts Clean Architecture's dependency rule (dependencies point
   inward only: interfaces depends on application/domain, never the
   reverse), even though it happened to work at runtime (no circular
   import, since `serializers.py` doesn't import anything from
   `dependencies.py`). Fixed by having the use case build its own small
   `_decision_facts()` dict locally instead of reaching into the
   interfaces layer for a coincidentally-similar-shaped function.

3. **Markdown-fenced JSON from LLM responses.** Anticipated rather than
   discovered (no live LLM to actually observe this from), based on
   well-known behavior of chat-completion models that wrap code blocks in
   ` ```json ... ``` ` even when instructed not to.
   `app/infrastructure/ai/common.py`'s `extract_json_object()` strips
   fences and falls back to locating the first top-level `{...}` block
   via regex if `json.loads()` on the stripped text still fails --
   covered by `test_openai_compatible_strips_markdown_fences`.

## Lessons for future providers

- Any new `AIProvider` implementation should accept a way to inject its
  transport/client dependency at construction time, the same way the two
  HTTP-backed providers here do -- it's what makes "no live LLM available"
  not a blocker to real test coverage.
- Keep the stub provider's fallback behavior and the real prompts'
  instructions philosophically consistent (flag uncertainty rather than
  fabricate) -- it means the "AI never decides, always flags for review"
  property holds the same way regardless of which provider a deployment
  has configured, and a developer testing against the free/offline stub
  is exercising the same safety posture a production LLM-backed
  deployment will.
