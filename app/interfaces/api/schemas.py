from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

_INC_101_EXAMPLE = {
    "incidentId": "INC-101",
    "towerId": "T-Delhi-101",
    "region": "Delhi",
    "affectedUsers": 15000,
    "vipCustomersAffected": True,
    "networkLoad": 94,
    "slaTier": "Gold",
    "maintenanceWindow": False,
    "weatherSeverity": "Moderate",
    "historicalFailures": 4,
    "incidentType": "Tower Down",
}


class IncidentEvaluateRequest(BaseModel):
    """Raw incident payload from an OSS monitoring system. Well-known fields
    used by the seeded rule pack are declared explicitly below for a useful
    Swagger schema; `extra="allow"` means additional fields a business-authored
    rule references are still accepted and evaluated even before they're added
    here."""

    model_config = ConfigDict(extra="allow", json_schema_extra={"example": _INC_101_EXAMPLE})

    incidentId: str = Field(..., description="Unique incident identifier from the source monitoring system")
    towerId: Optional[str] = Field(None, description="Affected tower/asset identifier")
    region: Optional[str] = Field(None, description="Geographic region -- used for rule-pack scoping and temporal rules")
    incidentType: Optional[str] = Field(None, description='e.g. "Tower Down", "Fiber Cut"')
    assetTier: Optional[str] = Field(None, description='e.g. "Core Router", "5G Core" -- drives the R028 asset-tier escalation')
    affectedUsers: Optional[int] = Field(None, ge=0, description="Number of subscribers impacted")
    vipCustomersAffected: Optional[bool] = Field(None, description="Whether any VIP-tier customer is impacted")
    networkLoad: Optional[float] = Field(None, ge=0, description="Current network load percentage")
    slaTier: Optional[str] = Field(None, description='"Gold" | "Silver" | "Bronze"')
    maintenanceWindow: Optional[bool] = Field(None, description="Whether an approved maintenance window is active for this asset")
    weatherSeverity: Optional[str] = Field(None, description='"Severe" triggers the dispatch-delay rule (R010)')
    historicalFailures: Optional[int] = Field(None, ge=0, description="Failures on this tower in the trailing 30 days")
    emergencyServicesAffected: Optional[bool] = Field(None, description="Hard-stop safety trigger (R008)")
    emergencyAlertSystemAffected: Optional[bool] = Field(None, description="Regulatory hard-stop trigger (R020)")
    packetLossPercent: Optional[float] = Field(None, ge=0, le=100)
    trafficSpikePercent: Optional[float] = Field(None, description="Percent above rolling baseline -- feeds DDoS detection (R015)")
    anomalyFlag: Optional[bool] = Field(None, description="Monitoring system's own confidence flag, required alongside trafficSpikePercent for R015")
    physicalTamperingDetected: Optional[bool] = Field(None, description="Security trigger (R032)")
    unauthorizedAccessDetected: Optional[bool] = Field(None, description="Security trigger (R032)")

    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Pre-supplied enrichment (context.* fields). Overrides the Context Aggregation Layer's aggregated values field-by-field -- useful for testing specific scenarios.",
    )
    degradedContext: Optional[bool] = Field(default=False, description="Force-mark this evaluation as degraded-context regardless of aggregation results")


class MatchedRuleModel(BaseModel):
    rule_code: str
    name: str
    family: str
    priority_weight: int
    severity_band: Optional[str] = None
    contribution_score: Optional[int] = None


class RejectedRuleModel(BaseModel):
    rule_code: str
    name: str
    reason: str


class ExecutionPlanStepModel(BaseModel):
    order: int
    action: str
    type: str
    condition: Optional[str] = None
    source: Optional[str] = None


class DecisionResponse(BaseModel):
    incidentId: str
    priority: Optional[str] = Field(None, description='"Critical" | "High" | "Medium" | "Low" -- categorical and deterministic')
    riskScore: int = Field(..., description="Additive secondary signal for triage ranking -- not the priority driver (design doc §3c)")
    riskBand: str = Field(..., description='"LOW" | "MEDIUM" | "HIGH" | "CRITICAL"')
    decision: Dict[str, Any] = Field(..., description="Merged action fields: dispatchEngineer, notifyNOC, rerouteTraffic, targetSLA, etc.")
    mitigations: Dict[str, Any] = Field(..., description="Operational mitigation flags, merged independently of `decision`")
    executionPlan: List[ExecutionPlanStepModel] = Field(..., description="Ordered plan honoring retry/fallback sequencing hints (design doc §3d)")
    matchedRules: List[MatchedRuleModel]
    rejectedRules: List[RejectedRuleModel]
    suppressedRules: List[Dict[str, Any]]
    complianceConstraints: List[Dict[str, Any]] = Field(..., description="COMPLIANCE-family rules applied after conflict resolution (design doc §6.5)")
    confidenceScore: float = Field(..., description="Data-completeness confidence, 0-100 -- distinct from rule-consensus strength (tradeoffs.md #13)")
    degradedContext: bool
    explanation: str
    aiExplanation: Optional[str] = Field(
        None,
        description="AI-generated plain-language narrative of THIS decision, only present when "
                    "?explainWithAi=true was passed. Strictly additive -- `explanation` above is always "
                    "the real, deterministic explanation and is never replaced or altered by this field. "
                    "Null if not requested, or if the AI provider call failed (never fails the request itself).",
    )

    model_config = ConfigDict(json_schema_extra={"example": {
        "incidentId": "INC-101",
        "priority": "Critical",
        "riskScore": 95,
        "riskBand": "CRITICAL",
        "decision": {"priority": "Critical", "dispatchEngineer": True, "targetSLA": "15 minutes"},
        "mitigations": {},
        "executionPlan": [{"order": 1, "action": "Dispatch Engineer", "type": "dispatchEngineer"}],
        "matchedRules": [{"rule_code": "R001", "name": "Mass user impact", "family": "NETWORK_IMPACT", "priority_weight": 90, "severity_band": "Critical", "contribution_score": 30}],
        "rejectedRules": [],
        "suppressedRules": [],
        "complianceConstraints": [],
        "confidenceScore": 100.0,
        "degradedContext": False,
        "explanation": "Critical because: Mass user impact (R001) ...",
    }})


# -- Phase 2: Auth -------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str = Field(..., description="Login email, unique per user")
    password: str = Field(..., min_length=8, description="At least 8 characters")
    fullName: str = ""
    roles: Optional[List[str]] = Field(None, description='Defaults to ["viewer"] if omitted')


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str = "bearer"
    expiresInMinutes: int


class RefreshRequest(BaseModel):
    refreshToken: str


class UserResponse(BaseModel):
    id: str
    email: str
    fullName: str
    roles: List[str]
    isActive: bool


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., description="Human-readable label, e.g. 'CI pipeline'")
    roles: Optional[List[str]] = Field(None, description='Defaults to ["viewer"] if omitted')


class ApiKeyCreateResponse(BaseModel):
    id: str
    apiKey: str = Field(..., description="The raw key -- shown exactly once, never retrievable again")
    keyPrefix: str
    name: str
    roles: List[str]


# -- Phase 2.5: dynamic Rule Management platform --------------------------
# Condition trees are JsonLogic-style (app/domain/value_objects/rule_condition.py,
# app/engine/) -- {"operator": [operand, ...]}, recursively nestable via
# "and"/"or"/"not" for ConditionGroup-equivalents, e.g.
# {"and": [{">": [{"var": "affectedUsers"}, 1000]}, {"==": [{"var": "region"}, "Delhi"]}]}.
# Modeled here as Dict[str, Any] (ConditionLeaf/ConditionGroup are the same
# recursive shape, not two separate schemas) rather than a fixed field/
# operator/value schema, since the engine's operator registry is itself
# runtime-pluggable (app/engine/evaluator_factory.py) -- constraining the
# Swagger schema to a fixed leaf shape would misdescribe what's actually accepted.

class ErrorResponse(BaseModel):
    detail: str


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int


class CreateRuleRequest(BaseModel):
    ruleCode: str
    name: str
    description: str = ""
    family: str = "OPERATIONAL_FEASIBILITY"
    familyOrder: int = 99
    priorityWeight: int = 50
    severityBand: Optional[str] = None
    contributionScore: Optional[int] = None
    conditions: Dict[str, Any] = Field(..., description="JsonLogic-style condition tree (ConditionLeaf/ConditionGroup)")
    exceptions: Optional[Dict[str, Any]] = None
    conflictGroup: Optional[str] = None
    conflictsWith: List[str] = Field(default_factory=list)
    isSuppressor: bool = False
    nonSuppressible: bool = False
    cooldownMinutes: int = 0
    actions: Dict[str, Any] = Field(default_factory=dict)
    mitigations: Dict[str, Any] = Field(default_factory=dict)
    sequencing: Optional[Dict[str, Any]] = None
    slaTarget: Optional[str] = None
    enabled: bool = True

    model_config = ConfigDict(json_schema_extra={"example": {
        "ruleCode": "R200", "name": "Custom high-load rule", "family": "NETWORK_IMPACT",
        "familyOrder": 2, "priorityWeight": 70, "severityBand": "High", "contributionScore": 20,
        "conditions": {">": [{"var": "networkLoad"}, 90]}, "actions": {"priority": "High", "notifyNOC": True},
    }})


class UpdateRuleRequest(BaseModel):
    """Partial update -- every field optional, only supplied fields change."""
    name: Optional[str] = None
    description: Optional[str] = None
    family: Optional[str] = None
    familyOrder: Optional[int] = None
    priorityWeight: Optional[int] = None
    severityBand: Optional[str] = None
    contributionScore: Optional[int] = None
    conditions: Optional[Dict[str, Any]] = None
    exceptions: Optional[Dict[str, Any]] = None
    conflictGroup: Optional[str] = None
    conflictsWith: Optional[List[str]] = None
    isSuppressor: Optional[bool] = None
    nonSuppressible: Optional[bool] = None
    cooldownMinutes: Optional[int] = None
    actions: Optional[Dict[str, Any]] = None
    mitigations: Optional[Dict[str, Any]] = None
    sequencing: Optional[Dict[str, Any]] = None
    slaTarget: Optional[str] = None
    enabled: Optional[bool] = None


class RuleResponse(BaseModel):
    id: Optional[str]
    ruleCode: str
    name: str
    description: str
    family: str
    familyOrder: int
    priorityWeight: int
    severityBand: Optional[str]
    contributionScore: Optional[int]
    conditions: Dict[str, Any]
    exceptions: Optional[Dict[str, Any]]
    conflictGroup: Optional[str]
    conflictsWith: List[str]
    isSuppressor: bool
    nonSuppressible: bool
    cooldownMinutes: int
    actions: Dict[str, Any]
    mitigations: Dict[str, Any]
    sequencing: Optional[Dict[str, Any]]
    slaTarget: Optional[str]
    ruleStatus: str
    enabled: bool


class BulkCreateRulesRequest(BaseModel):
    rules: List[CreateRuleRequest]


class ValidateRuleRequest(CreateRuleRequest):
    pass


class ValidationResultResponse(BaseModel):
    isValid: bool
    errors: List[str]


class CreateRulePackRequest(BaseModel):
    name: str
    region: Optional[str] = None
    tenantId: Optional[str] = None
    rules: List[CreateRuleRequest] = Field(default_factory=list)


class UpdateRulePackRequest(BaseModel):
    name: Optional[str] = None
    region: Optional[str] = None
    tenantId: Optional[str] = None
    expectedLockVersion: Optional[int] = Field(
        None, description="Optimistic concurrency token from a prior GET's `lockVersion` (Phase 5). "
                           "If given and it no longer matches the pack's current lockVersion, the request "
                           "fails with 409 Conflict instead of silently overwriting someone else's change.",
    )


class ImportRulePackRequest(BaseModel):
    name: str
    version: Optional[int] = None
    region: Optional[str] = None
    tenantId: Optional[str] = None
    rules: List[CreateRuleRequest] = Field(default_factory=list)


class RulePackResponse(BaseModel):
    id: Optional[str]
    name: str
    version: int
    status: str
    region: Optional[str]
    tenantId: Optional[str]
    parentVersion: Optional[int]
    createdBy: str
    ruleCount: int
    activatedAt: Optional[str]
    lockVersion: int = Field(1, description="Optimistic concurrency token (Phase 5) -- pass back as `expectedLockVersion` on PATCH/publish/activate/rollback/delete to guard against a lost update.")


class RollbackRulePackRequest(BaseModel):
    reason: Optional[str] = None
    expectedLockVersion: Optional[int] = Field(None, description="See RulePackResponse.lockVersion -- checked against the version being rolled back FROM.")


class ActivateRulePackRequest(BaseModel):
    reason: Optional[str] = None
    expectedLockVersion: Optional[int] = Field(None, description="See RulePackResponse.lockVersion.")


class DeleteRulePackRequest(BaseModel):
    reason: Optional[str] = None
    expectedLockVersion: Optional[int] = Field(None, description="See RulePackResponse.lockVersion.")


class IncidentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="allow", json_schema_extra={"example": _INC_101_EXAMPLE})

    incidentId: str
    region: Optional[str] = None
    tenantId: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    evaluate: bool = Field(True, description="If true (default), immediately runs the incident through the Decision Engine and returns the resulting decision alongside the persisted incident.")


class IncidentBulkCreateRequest(BaseModel):
    incidents: List[IncidentCreateRequest]
    evaluate: bool = True


class IncidentResponse(BaseModel):
    incidentId: str
    status: str
    region: Optional[str]
    tenantId: Optional[str]
    payload: Dict[str, Any]
    createdAt: Optional[str]
    decision: Optional[DecisionResponse] = None


# -- Phase 3: AI-assisted rule authoring ----------------------------------

class GenerateRuleRequest(BaseModel):
    description: str = Field(..., min_length=3, description="Plain-language description of the rule to draft")
    family: Optional[str] = None
    region: Optional[str] = None
    samplePayload: Optional[Dict[str, Any]] = Field(None, description="Example incident payload the rule should consider")

    model_config = ConfigDict(json_schema_extra={"example": {
        "description": "If affected users is greater than 5000, mark priority critical and dispatch an engineer",
    }})


class GenerateRuleResponse(BaseModel):
    rule: Dict[str, Any] = Field(..., description="Draft rule payload, shaped like CreateRuleRequest -- NOT persisted. Review it, then POST /api/v1/rules to actually create it.")
    isValid: bool
    validationErrors: List[str]
    aiProvider: str


class DocumentRuleRequest(BaseModel):
    ruleId: Optional[str] = Field(None, description="Existing rule id to document -- alternative to `rule`")
    rule: Optional[CreateRuleRequest] = Field(None, description="An inline rule payload to document -- alternative to `ruleId`")


class DocumentRuleResponse(BaseModel):
    documentation: str
    aiProvider: str


class ExplainDecisionResponse(BaseModel):
    incidentId: str
    deterministicExplanation: str = Field(..., description="Always available, zero AI involvement -- ExplainabilityBuilder's output (same as DecisionResponse.explanation)")
    aiExplanation: str = Field(..., description="AI-generated plain-language narrative, strictly additive -- see docs/ai-assist.md")
    aiProvider: str


# -- Phase 4: Simulation + bulk evaluation --------------------------------
# Rule-pack references throughout this section follow the same pattern:
# `rulePackId` (a specific versioned pack, including a never-activated
# Draft) OR `rulePackName`+`rulePackVersion` OR `rulePackName` alone (that
# name's currently-active version) OR nothing at all, which falls back to
# whatever RuleRepository.get_active() actually serves on the real
# incident-evaluation hot path -- see rule_pack_resolution.py.

class RulePackRefResponse(BaseModel):
    source: str = Field(..., description='"hot_path_active" (the same pack POST /api/v1/incidents/evaluate would use) or "rule_pack" (a specific versioned pack resolved via rulePackId/rulePackName)')
    id: Optional[str]
    name: str
    version: int
    status: str
    region: Optional[str]


class SimulateRequest(BaseModel):
    incident: IncidentEvaluateRequest = Field(..., description="Incident payload to simulate -- same shape as POST /api/v1/incidents/evaluate")
    rulePackId: Optional[str] = Field(None, description="Simulate against this exact rule-pack version (including an unpublished Draft)")
    rulePackName: Optional[str] = None
    rulePackVersion: Optional[int] = None
    region: Optional[str] = None
    tenantId: Optional[str] = None

    model_config = ConfigDict(json_schema_extra={"example": {
        "incident": _INC_101_EXAMPLE,
    }})


class SimulateResponse(BaseModel):
    decision: DecisionResponse
    rulePackUsed: RulePackRefResponse
    persisted: bool = Field(False, description="Simulation never persists a decision -- always false")


class ReplaySimulationRequest(BaseModel):
    incidentId: str = Field(..., description="A previously-persisted incident (created via POST /api/v1/incidents or /evaluate) to re-run")
    rulePackId: Optional[str] = None
    rulePackName: Optional[str] = None
    rulePackVersion: Optional[int] = None


class ReplaySimulationResponse(BaseModel):
    incidentId: str
    originalDecision: Optional[DecisionResponse] = Field(None, description="The decision on record for this incident, if any -- null if it was never evaluated before")
    replayedDecision: DecisionResponse
    rulePackUsed: RulePackRefResponse
    differs: bool = Field(..., description="True if the replayed decision's priority, actions, or matched rules differ from the original")
    differences: List[str]


class CompareRulePacksRequest(BaseModel):
    incidentIds: List[str] = Field(default_factory=list, description="Persisted incidents to replay through both packs")
    incidents: List[IncidentEvaluateRequest] = Field(default_factory=list, description="Inline incident payloads to run through both packs, in addition to incidentIds")
    baselineRulePackId: Optional[str] = Field(None, description="Defaults to the currently-active hot-path pack if omitted")
    baselineRulePackName: Optional[str] = None
    baselineRulePackVersion: Optional[int] = None
    candidateRulePackId: Optional[str] = Field(None, description="Required (with or instead: candidateRulePackName[+Version]) -- the pack being compared against the baseline")
    candidateRulePackName: Optional[str] = None
    candidateRulePackVersion: Optional[int] = None
    region: Optional[str] = None
    tenantId: Optional[str] = None


class RulePackDiffEntryResponse(BaseModel):
    incidentId: str
    baselinePriority: Optional[str]
    candidatePriority: Optional[str]
    baselineDecision: Dict[str, Any]
    candidateDecision: Dict[str, Any]
    differs: bool


class CompareRulePacksResponse(BaseModel):
    baseline: RulePackRefResponse
    candidate: RulePackRefResponse
    totalIncidents: int
    differingCount: int
    diffs: List[RulePackDiffEntryResponse]


class BulkEvaluateRequest(BaseModel):
    incidents: List[IncidentEvaluateRequest] = Field(..., min_length=1)
    persist: bool = Field(True, description="If true (default), each decision is persisted exactly like POST /api/v1/incidents/evaluate. If false, this is a pure dry-run bulk simulation against the active rule pack -- nothing is written.")
    region: Optional[str] = Field(None, description="Fallback region for any incident that doesn't specify its own")
    tenantId: Optional[str] = None


class BulkEvaluateResultEntryResponse(BaseModel):
    incidentId: Optional[str]
    success: bool
    priority: Optional[str] = None
    riskBand: Optional[str] = None
    error: Optional[str] = None


class BulkEvaluateResponse(BaseModel):
    totalSubmitted: int
    succeeded: int
    failed: int
    executionTimeMs: float
    averageTimeMsPerIncident: float
    priorityDistribution: Dict[str, int]
    riskBandDistribution: Dict[str, int]
    results: List[BulkEvaluateResultEntryResponse]


class DecisionsDistributionResponse(BaseModel):
    totalDecisions: int
    priorityDistribution: Dict[str, int]
    riskBandDistribution: Dict[str, int]
    averageRiskScore: float
    averageConfidenceScore: float
    degradedContextCount: int
