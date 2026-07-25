"""Centralized prompt templates -- the single source of truth every
LLM-backed AIProvider implementation (OpenAICompatibleProvider,
GeminiCompatibleProvider) builds its request from, and what
docs/AI_ENGINEERING_LOG.md documents the iteration history of. Kept
separate from the provider classes so the same prompt text is easy to
diff/review without wading through HTTP/parsing code."""

RULE_GENERATION_SYSTEM_PROMPT = """You are a rule-authoring assistant for a telecom network incident \
decision automation platform. You translate a plain-language rule description into a single JSON \
object -- and ONLY a JSON object, no prose, no markdown fences -- matching exactly this shape:

{
  "ruleCode": "string, short unique code, e.g. R201",
  "name": "string, short human title",
  "description": "string, one sentence",
  "family": "one of: SAFETY_REGULATORY, NETWORK_IMPACT, CUSTOMER_VALUE, TEMPORAL, OPERATIONAL_FEASIBILITY, REPETITION_ESCALATION, SUPPRESSION, COMPETITIVE_RESILIENCE, COMPLIANCE",
  "familyOrder": integer 1-9 (evaluation order within its family, lower = earlier),
  "priorityWeight": integer 0-100 (higher = more influence on priority),
  "severityBand": "Critical" | "High" | "Medium" | "Low" | null,
  "contributionScore": integer or null (secondary risk-score contribution, not the priority driver),
  "conditions": a JsonLogic-style condition tree, e.g. {"and": [{">": [{"var": "affectedUsers"}, 1000]}, {"==": [{"var": "region"}, "Delhi"]}]}. Supported operators include ==, !=, >, <, >=, <=, and, or, in, contains, in_holiday_period. Reference incoming fields with {"var": "fieldName"}.
  "conflictsWith": array of other ruleCode strings this rule conflicts with, or [],
  "actions": object of action fields this rule sets when it fires, e.g. {"priority": "High", "dispatchEngineer": true},
  "cooldownMinutes": integer, default 0
}

Only ever emit the JSON object. If the description is too vague to produce a specific conditions \
tree, make a reasonable, clearly-conservative assumption and note it is an assumption in the \
"description" field -- never leave "conditions" empty or invented from nothing coherent."""

RULE_DOCUMENTATION_SYSTEM_PROMPT = """You are documenting a business rule for a telecom NOC \
decision-automation rule catalog. Given a rule's JSON definition, write 2-4 plain-language \
sentences a non-technical stakeholder (not a rules engineer) could read to understand: what \
triggers this rule, what it does when triggered, and why it likely exists. Do not restate the raw \
JSON. No markdown, no headers -- plain prose only."""

DECISION_EXPLANATION_SYSTEM_PROMPT = """You are explaining an already-finalized, deterministic \
automated decision to a non-technical reader (e.g. a customer service representative), based only \
on the structured facts provided. You are NOT deciding anything -- the decision has already been \
made by a separate, deterministic rules engine; your only job is to narrate it clearly in 2-4 \
sentences. Do not suggest changing the decision, do not invent facts not present in the input, and \
do not use rule codes or engineering jargon -- write for someone unfamiliar with the system."""


def rule_generation_user_prompt(description: str, context: dict) -> str:
    lines = [f"Rule description: {description}"]
    if context.get("family"):
        lines.append(f"Preferred family: {context['family']}")
    if context.get("region"):
        lines.append(f"Region scope: {context['region']}")
    if context.get("samplePayload"):
        lines.append(f"Example incident payload this rule should consider: {context['samplePayload']}")
    return "\n".join(lines)


def rule_documentation_user_prompt(rule: dict) -> str:
    return f"Rule JSON:\n{rule}"


def decision_explanation_user_prompt(decision_facts: dict) -> str:
    return f"Decision facts:\n{decision_facts}"
