from typing import Any, Dict, Optional
from app.domain.entities.decision import Decision
from app.domain.entities.rule import Rule
from app.domain.entities.rule_pack import RulePack
from app.domain.entities.incident import Incident
from app.application.use_cases.simulate_rules import WhatIfResult
from app.application.use_cases.replay_simulation import ReplayResult
from app.application.use_cases.compare_rule_packs import CompareResult
from app.application.use_cases.bulk_evaluate import BulkEvaluateResult
from app.application.use_cases.decision_distribution import DistributionResult


def decision_to_dict(decision: Decision, ai_explanation: Optional[str] = None) -> Dict[str, Any]:
    """Single source of truth for turning a Decision entity into the API
    response shape -- used by both incident_router (submission) and
    decision_router (retrieval) so the two can never silently drift apart.

    ai_explanation is optional and defaults to None -- every existing call
    site (decision_router, incident_to_dict, bulk evaluate) is unaffected
    and just gets `"aiExplanation": null`. Only incident_router's
    POST /evaluate passes a real value, and only when the caller opted in
    via ?explainWithAi=true."""
    return {
        "incidentId": decision.incident_id,
        "priority": decision.priority,
        "riskScore": decision.risk_score,
        "riskBand": decision.risk_band,
        "decision": decision.actions,
        "mitigations": decision.mitigations,
        "executionPlan": decision.execution_plan,
        "matchedRules": [r.__dict__ for r in decision.matched_rules],
        "rejectedRules": [r.__dict__ for r in decision.rejected_rules],
        "suppressedRules": decision.suppressed_rules,
        "complianceConstraints": decision.compliance_constraints,
        "confidenceScore": decision.confidence_score,
        "degradedContext": decision.degraded_context,
        "aiExplanation": ai_explanation,
        "explanation": decision.explanation,
    }


def rule_to_dict(rule: Rule) -> Dict[str, Any]:
    return {
        "id": rule.id,
        "ruleCode": rule.rule_code,
        "name": rule.name,
        "description": rule.description,
        "family": rule.family,
        "familyOrder": rule.family_order,
        "priorityWeight": rule.priority_weight,
        "severityBand": rule.severity_band,
        "contributionScore": rule.contribution_score,
        "conditions": rule.conditions.tree,
        "exceptions": rule.exceptions.tree if rule.exceptions else None,
        "conflictGroup": rule.conflict_group,
        "conflictsWith": list(rule.conflicts_with or []),
        "isSuppressor": rule.is_suppressor,
        "nonSuppressible": rule.non_suppressible,
        "cooldownMinutes": rule.cooldown_minutes,
        "actions": rule.actions,
        "mitigations": rule.mitigations,
        "sequencing": rule.sequencing,
        "slaTarget": rule.sla_target,
        "ruleStatus": rule.rule_status,
        "enabled": rule.enabled,
    }


def rule_pack_to_dict(pack: RulePack) -> Dict[str, Any]:
    return {
        "id": pack.id,
        "name": pack.name,
        "version": pack.version,
        "status": pack.status,
        "region": pack.region,
        "tenantId": pack.tenant_id,
        "parentVersion": pack.parent_version,
        "createdBy": pack.created_by,
        "ruleCount": len(pack.rules),
        "activatedAt": pack.activated_at.isoformat() if pack.activated_at else None,
        "lockVersion": pack.lock_version,
    }


def incident_to_dict(incident: Incident, decision: Optional[Decision] = None, ai_explanation: Optional[str] = None) -> Dict[str, Any]:
    """ai_explanation is optional and defaults to None, same convention as
    decision_to_dict -- every existing call site is unaffected. Only
    incident_router's POST /incidents/bulk passes a real value per-incident,
    and only when the caller opted in via ?explainWithAi=true."""
    return {
        "incidentId": incident.incident_id,
        "status": incident.status,
        "region": incident.region,
        "tenantId": incident.tenant_id,
        "payload": incident.payload,
        "createdAt": incident.created_at.isoformat() if incident.created_at else None,
        "decision": decision_to_dict(decision, ai_explanation=ai_explanation) if decision is not None else None,
    }


# -- Phase 4: Simulation + bulk evaluation --------------------------------

def what_if_result_to_dict(result: WhatIfResult) -> Dict[str, Any]:
    return {
        "decision": decision_to_dict(result.decision),
        "rulePackUsed": result.rule_pack_used,
        "persisted": False,
    }


def replay_result_to_dict(result: ReplayResult) -> Dict[str, Any]:
    return {
        "incidentId": result.incident_id,
        "originalDecision": decision_to_dict(result.original_decision) if result.original_decision else None,
        "replayedDecision": decision_to_dict(result.replayed_decision),
        "rulePackUsed": result.rule_pack_used,
        "differs": result.differs,
        "differences": result.differences,
    }


def compare_result_to_dict(result: CompareResult) -> Dict[str, Any]:
    return {
        "baseline": result.baseline,
        "candidate": result.candidate,
        "totalIncidents": result.total_incidents,
        "differingCount": result.differing_count,
        "diffs": [
            {
                "incidentId": d.incident_id,
                "baselinePriority": d.baseline_priority,
                "candidatePriority": d.candidate_priority,
                "baselineDecision": d.baseline_decision,
                "candidateDecision": d.candidate_decision,
                "differs": d.differs,
            }
            for d in result.diffs
        ],
    }


def bulk_evaluate_result_to_dict(result: BulkEvaluateResult) -> Dict[str, Any]:
    return {
        "totalSubmitted": result.total,
        "succeeded": result.succeeded,
        "failed": result.failed,
        "executionTimeMs": result.execution_time_ms,
        "averageTimeMsPerIncident": result.average_time_ms_per_incident,
        "priorityDistribution": result.priority_distribution,
        "riskBandDistribution": result.risk_band_distribution,
        "results": [
            {
                "incidentId": r.incident_id,
                "success": r.success,
                "priority": r.priority,
                "riskBand": r.risk_band,
                "error": r.error,
            }
            for r in result.results
        ],
    }


def distribution_result_to_dict(result: DistributionResult) -> Dict[str, Any]:
    return {
        "totalDecisions": result.total_decisions,
        "priorityDistribution": result.priority_distribution,
        "riskBandDistribution": result.risk_band_distribution,
        "averageRiskScore": result.average_risk_score,
        "averageConfidenceScore": result.average_confidence_score,
        "degradedContextCount": result.degraded_context_count,
    }
