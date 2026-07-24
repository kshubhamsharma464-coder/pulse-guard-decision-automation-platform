"""Composition root -- shared singletons wired once here and imported by
routers. Repository selection is driven by Settings.persistence_backend
("memory", the default, or "postgres"): every repository below implements
the SAME domain interface either way, so nothing in application/ or
domain/ changes based on this switch -- see docs/persistence.md.

Scope note: `rule_repository` (the hot incident-evaluation path) is
switched by a SEPARATE setting, `Settings.rule_source` ("static", the
default, or "dynamic"), not by persistence_backend -- see
docs/rule-management.md. "static" is exactly Phase 1's behavior: the
CompositeRuleRepository merging the base pack + 6 additive fixture packs,
142 rules total, byte-identical to every existing test's expectations.
"dynamic" (requires persistence_backend="postgres") swaps it for
PostgresRuleRepository wrapped in a cache-fronted RuleCache -- rules and
rule packs created/published/activated/rolled back via /api/v1/rules and
/api/v1/rule-packs become the live evaluation source with zero
application restart."""

from app.core.settings import get_settings
from app.infrastructure.repositories.in_memory_rule_repository import InMemoryRuleRepository
from app.infrastructure.repositories.composite_rule_repository import CompositeRuleRepository
from app.infrastructure.repositories.sla_rule_pack_loader import load_sla_rules, load_sla_matrix
from app.infrastructure.repositories.vast_rule_pack_loader import load_vast_rules
from app.infrastructure.repositories.csr_sla_rule_pack_loader import load_csr_sla_rules
from app.infrastructure.repositories.historical_pattern_rule_pack_loader import load_historical_pattern_rules
from app.infrastructure.repositories.net_inf_rule_pack_loader import load_net_inf_rules
from app.infrastructure.repositories.industry_sop_rule_pack_loader import load_industry_sop_rules
from app.infrastructure.repositories.in_memory_decision_repository import InMemoryDecisionRepository
from app.infrastructure.repositories.in_memory_rule_pack_repository import InMemoryRulePackRepository
from app.infrastructure.repositories.in_memory_manual_override_repository import InMemoryManualOverrideRepository
from app.infrastructure.repositories.in_memory_escalation_repository import InMemoryEscalationRepository
from app.infrastructure.repositories.in_memory_escalation_policy_repository import InMemoryEscalationPolicyRepository
from app.infrastructure.repositories.in_memory_audit_log_repository import InMemoryAuditLogRepository
from app.infrastructure.repositories.in_memory_request_log_repository import InMemoryRequestLogRepository
from app.infrastructure.repositories.in_memory_user_repository import InMemoryUserRepository
from app.infrastructure.repositories.in_memory_role_repository import InMemoryRoleRepository
from app.infrastructure.repositories.in_memory_permission_repository import InMemoryPermissionRepository
from app.infrastructure.repositories.in_memory_api_key_repository import InMemoryAPIKeyRepository
from app.infrastructure.repositories.in_memory_incident_repository import InMemoryIncidentRepository
from app.infrastructure.cache.in_memory_cache_refresh_notifier import InMemoryCacheRefreshNotifier
from app.infrastructure.cache.rule_cache import RuleCache

from app.infrastructure.external.historical_context_provider import HistoricalContextProvider
from app.infrastructure.external.crm_provider import CrmProvider
from app.infrastructure.external.regional_policy_provider import RegionalPolicyProvider
from app.infrastructure.external.workforce_provider import WorkforceProvider
from app.infrastructure.external.vendor_kb_provider import VendorKnowledgeBaseProvider
from app.infrastructure.external.incident_correlation_provider import IncidentCorrelationProvider
from app.infrastructure.external.competitive_intel_provider import CompetitiveIntelProvider
from app.infrastructure.external.social_listening_provider import SocialListeningProvider

from app.domain.services.context_aggregation_service import ContextAggregationService
from app.domain.services.sla_matrix_lookup import SlaMatrixLookup
from app.application.orchestrator import PipelineOrchestrator
from app.application.use_cases.evaluate_incident import EvaluateIncidentUseCase
from app.application.use_cases.validate_rule_pack import ValidateRulePackUseCase
from app.application.use_cases.rollback_rule_pack import RollbackRulePackUseCase
from app.application.use_cases.override_decision import OverrideDecisionUseCase
from app.application.use_cases.acknowledge_escalation import AcknowledgeEscalationUseCase
from app.application.use_cases.register_user import RegisterUserUseCase
from app.application.use_cases.authenticate_user import AuthenticateUserUseCase
from app.application.use_cases.create_api_key import CreateApiKeyUseCase
from app.application.use_cases.rule_pack_lifecycle import (
    CreateRulePackUseCase, UpdateRulePackMetadataUseCase, SoftDeleteRulePackUseCase,
    PublishRulePackUseCase, ActivateRulePackUseCase, ImportRulePackUseCase, ExportRulePackUseCase,
)
from app.application.use_cases.manage_rules import (
    CreateRuleUseCase, GetRuleUseCase, ListRulesUseCase, UpdateRuleUseCase, DeleteRuleUseCase,
    BulkCreateRulesUseCase, ValidateRuleUseCase, RuleHistoryUseCase,
)
from app.application.use_cases.manage_incidents import (
    CreateIncidentUseCase, GetIncidentUseCase, ListIncidentsUseCase, BulkCreateIncidentsUseCase,
)
from app.infrastructure.ai.factory import create_ai_provider
from app.application.use_cases.generate_rule_from_description import GenerateRuleFromDescriptionUseCase
from app.application.use_cases.document_rule import DocumentRuleUseCase
from app.application.use_cases.explain_decision_ai import ExplainDecisionAIUseCase
from app.application.use_cases.simulate_rules import WhatIfSimulationUseCase
from app.application.use_cases.replay_simulation import ReplaySimulationUseCase
from app.application.use_cases.compare_rule_packs import CompareRulePacksUseCase
from app.application.use_cases.bulk_evaluate import BulkEvaluateUseCase
from app.application.use_cases.decision_distribution import DecisionDistributionUseCase

settings = get_settings()

if settings.persistence_backend == "postgres":
    from sqlalchemy.orm import sessionmaker
    from app.infrastructure.db.session import get_engine, get_sessionmaker
    from app.infrastructure.repositories.postgres_decision_repository import PostgresDecisionRepository
    from app.infrastructure.repositories.postgres_rule_pack_repository import PostgresRulePackRepository
    from app.infrastructure.repositories.postgres_manual_override_repository import PostgresManualOverrideRepository
    from app.infrastructure.repositories.postgres_escalation_repository import PostgresEscalationRepository
    from app.infrastructure.repositories.postgres_escalation_policy_repository import PostgresEscalationPolicyRepository
    from app.infrastructure.repositories.postgres_audit_log_repository import PostgresAuditLogRepository
    from app.infrastructure.repositories.postgres_request_log_repository import PostgresRequestLogRepository
    from app.infrastructure.repositories.postgres_user_repository import PostgresUserRepository
    from app.infrastructure.repositories.postgres_role_repository import PostgresRoleRepository
    from app.infrastructure.repositories.postgres_permission_repository import PostgresPermissionRepository
    from app.infrastructure.repositories.postgres_api_key_repository import PostgresAPIKeyRepository
    from app.infrastructure.repositories.postgres_incident_repository import PostgresIncidentRepository
    from app.infrastructure.repositories.postgres_rule_repository import PostgresRuleRepository

    _engine = get_engine(
        settings.database_url, echo=settings.database_echo,
        pool_size=settings.database_pool_size, max_overflow=settings.database_max_overflow,
    )
    _session_factory: sessionmaker = get_sessionmaker(_engine)

# Base pack (35 rules, unchanged) + the customer_sla_rules_telecom pack (12
# transpiled rules) merged into one active pack so they're evaluated and
# conflict-resolved together (composite_rule_repository.py explains why this
# has to be one pass, not two). InMemoryRuleRepository itself is untouched --
# every test that constructs it directly still sees exactly 35 rules.
_base_pack = InMemoryRuleRepository().get_active()
_sla_rules = load_sla_rules()
_vast_rules = load_vast_rules()
_csr_sla_rules = load_csr_sla_rules()
_historical_pattern_rules = load_historical_pattern_rules()
_net_inf_rules = load_net_inf_rules()
_industry_sop_rules = load_industry_sop_rules()
_static_rule_repository = CompositeRuleRepository(
    name=_base_pack.name,
    version=_base_pack.version + 1,
    region=_base_pack.region,
    rule_groups=[_base_pack.rules, _sla_rules, _vast_rules, _csr_sla_rules, _historical_pattern_rules, _net_inf_rules, _industry_sop_rules],
)
sla_matrix_lookup = SlaMatrixLookup(load_sla_matrix())

# Always constructed (cheap, in-memory) so routers/use cases can always
# depend on them even when rule_source="static" and nothing reads through
# the cache yet -- see app/infrastructure/cache/rule_cache.py.
#
# distributed_cache_backend (Phase 5, docs/policy-platform.md) is only
# built when Settings.cache_backend="redis" -- redis.Redis.from_url()
# doesn't connect eagerly, so this never fails at import time even if no
# Redis server is reachable; every real failure is caught per-call inside
# RedisCacheBackend and degrades to the PostgreSQL/local-memory fallback
# path instead of raising. Default ("memory") constructs nothing here and
# RuleCache behaves byte-identically to every version before Phase 5.
distributed_cache_backend = None
if settings.cache_backend == "redis":
    from app.infrastructure.cache.redis_client_factory import create_redis_client
    from app.infrastructure.cache.redis_cache_backend import RedisCacheBackend
    distributed_cache_backend = RedisCacheBackend(
        create_redis_client(settings),
        key_prefix=settings.redis_key_prefix,
        snapshot_ttl_seconds=settings.redis_snapshot_max_age_seconds,
    )

cache_refresh_notifier = InMemoryCacheRefreshNotifier()
rule_cache = RuleCache(
    notifier=cache_refresh_notifier, ttl_seconds=settings.rule_cache_ttl_seconds,
    distributed_backend=distributed_cache_backend, cache_key=settings.dynamic_rule_set_name,
)

if settings.persistence_backend == "postgres":
    decision_repository = PostgresDecisionRepository(_session_factory)
    rule_pack_repository = PostgresRulePackRepository(_session_factory)
    manual_override_repository = PostgresManualOverrideRepository(_session_factory)
    escalation_repository = PostgresEscalationRepository(_session_factory)
    escalation_policy_repository = PostgresEscalationPolicyRepository(_session_factory)
    audit_log_repository = PostgresAuditLogRepository(_session_factory)
    request_log_repository = PostgresRequestLogRepository(_session_factory)
    # Postgres starts with no roles/permissions/users seeded -- run
    # scripts/seed_default_roles_permissions.py once after migrating (see
    # docs/auth.md). The in-memory backend below seeds them in its own
    # constructor so local/test runs work with zero setup.
    user_repository = PostgresUserRepository(_session_factory)
    role_repository = PostgresRoleRepository(_session_factory)
    permission_repository = PostgresPermissionRepository(_session_factory)
    api_key_repository = PostgresAPIKeyRepository(_session_factory)
    incident_repository = PostgresIncidentRepository(_session_factory)
else:
    decision_repository = InMemoryDecisionRepository()
    rule_pack_repository = InMemoryRulePackRepository()
    manual_override_repository = InMemoryManualOverrideRepository()
    escalation_repository = InMemoryEscalationRepository()
    escalation_policy_repository = InMemoryEscalationPolicyRepository()
    audit_log_repository = InMemoryAuditLogRepository()
    request_log_repository = InMemoryRequestLogRepository()
    user_repository = InMemoryUserRepository()
    role_repository = InMemoryRoleRepository()
    permission_repository = InMemoryPermissionRepository()
    api_key_repository = InMemoryAPIKeyRepository()
    incident_repository = InMemoryIncidentRepository()

# rule_repository: the hot evaluation path's source. "static" (default) --
# exactly Phase 1's fixed 142-rule composite, byte-identical to every
# existing test. "dynamic" -- Postgres-backed, cache-fronted, live-
# updatable via /api/v1/rules and /api/v1/rule-packs (docs/rule-management.md).
if settings.rule_source == "dynamic":
    if settings.persistence_backend != "postgres":
        raise RuntimeError(
            "RULE_SOURCE=dynamic requires PERSISTENCE_BACKEND=postgres -- "
            "the dynamic rule source reads rule packs from Postgres."
        )
    rule_repository = PostgresRuleRepository(_session_factory, rule_set_name=settings.dynamic_rule_set_name, cache=rule_cache)
    # Lets cache-refresh events (publish/activate/rollback/delete) eagerly
    # rebuild-and-swap (including a Redis write-through) instead of only
    # invalidating this process's local copy -- see RuleCache's module
    # docstring's "bind_loader()" section. region/tenant=None matches this
    # platform's current single-global-pack scope (dynamic_rule_set_name);
    # a genuinely multi-region/multi-tenant deployment would bind one
    # cache+loader pair per region/tenant instead of one global pair.
    rule_cache.bind_loader(lambda: rule_repository.load_from_source(region=None, tenant=None))
else:
    rule_repository = _static_rule_repository

context_aggregation_service = ContextAggregationService(providers=[
    HistoricalContextProvider(),
    CrmProvider(),
    RegionalPolicyProvider(),
    WorkforceProvider(),
    VendorKnowledgeBaseProvider(),
    IncidentCorrelationProvider(),
    CompetitiveIntelProvider(),
    SocialListeningProvider(),
])

evaluate_incident_use_case = EvaluateIncidentUseCase(
    rule_repository=rule_repository,
    orchestrator=PipelineOrchestrator(sla_matrix_lookup=sla_matrix_lookup),
    context_aggregation_service=context_aggregation_service,
    decision_repository=decision_repository,
)
validate_rule_pack_use_case = ValidateRulePackUseCase()
rollback_rule_pack_use_case = RollbackRulePackUseCase(rule_pack_repository)
override_decision_use_case = OverrideDecisionUseCase(manual_override_repository)
acknowledge_escalation_use_case = AcknowledgeEscalationUseCase()

register_user_use_case = RegisterUserUseCase(user_repository, role_repository)
authenticate_user_use_case = AuthenticateUserUseCase(user_repository)
create_api_key_use_case = CreateApiKeyUseCase(api_key_repository)

# -- Dynamic Rule Management platform (docs/rule-management.md) ---------
# Every mutating use case below is wired with cache_refresh_notifier +
# audit_log_repository so publish/activate/rollback/delete actually
# refresh the cache and leave an audit trail in every deployment, not
# just when a caller happens to pass them in.
create_rule_pack_use_case = CreateRulePackUseCase(rule_pack_repository, audit_log_repository)
update_rule_pack_metadata_use_case = UpdateRulePackMetadataUseCase(rule_pack_repository, audit_log_repository)
soft_delete_rule_pack_use_case = SoftDeleteRulePackUseCase(
    rule_pack_repository, cache=rule_cache, notifier=cache_refresh_notifier, audit_log_repository=audit_log_repository,
)
publish_rule_pack_use_case = PublishRulePackUseCase(
    rule_pack_repository, validator=validate_rule_pack_use_case, audit_log_repository=audit_log_repository,
)
activate_rule_pack_use_case = ActivateRulePackUseCase(
    rule_pack_repository, cache=rule_cache, notifier=cache_refresh_notifier, audit_log_repository=audit_log_repository,
)
import_rule_pack_use_case = ImportRulePackUseCase(rule_pack_repository, audit_log_repository)
export_rule_pack_use_case = ExportRulePackUseCase(rule_pack_repository)

# rollback_rule_pack_use_case constructed above (Phase 1) with just a
# repository; re-wire it here with the same cache/notifier/audit
# collaborators so the HTTP-exposed rollback actually has real side
# effects. (The original object above is left as-is for anything that may
# still hold a reference to it -- nothing currently does.)
rollback_rule_pack_use_case = RollbackRulePackUseCase(
    rule_pack_repository, cache=rule_cache, notifier=cache_refresh_notifier, audit_log_repository=audit_log_repository,
)

create_rule_use_case = CreateRuleUseCase(rule_pack_repository, audit_log_repository)
get_rule_use_case = GetRuleUseCase(rule_pack_repository)
list_rules_use_case = ListRulesUseCase(rule_pack_repository)
update_rule_use_case = UpdateRuleUseCase(rule_pack_repository, audit_log_repository)
delete_rule_use_case = DeleteRuleUseCase(rule_pack_repository, audit_log_repository)
bulk_create_rules_use_case = BulkCreateRulesUseCase(create_rule_use_case)
validate_rule_use_case = ValidateRuleUseCase()
rule_history_use_case = RuleHistoryUseCase(audit_log_repository)

create_incident_use_case = CreateIncidentUseCase(incident_repository, evaluate_incident_use_case)
get_incident_use_case = GetIncidentUseCase(incident_repository)
list_incidents_use_case = ListIncidentsUseCase(incident_repository)
bulk_create_incidents_use_case = BulkCreateIncidentsUseCase(create_incident_use_case)

# -- AI-assisted rule authoring (Phase 3, docs/ai-assist.md) -------------
# Settings.ai_provider selects the concrete provider (default "stub" --
# deterministic, offline, zero configuration). Every AI-assisted use case
# below is additive: nothing on the deterministic decision path
# (evaluate_incident_use_case, PipelineOrchestrator, PolicyEngine, ...)
# references ai_provider or any of these use cases.
ai_provider = create_ai_provider(settings)
generate_rule_from_description_use_case = GenerateRuleFromDescriptionUseCase(ai_provider, validate_rule_use_case)
document_rule_use_case = DocumentRuleUseCase(ai_provider)
explain_decision_ai_use_case = ExplainDecisionAIUseCase(ai_provider)

# -- Simulation + bulk evaluation (Phase 4, docs/simulation.md) ----------
# what_if/replay/compare all resolve rule packs through the SAME
# rule_repository (the real hot-path source) and rule_pack_repository (the
# dynamic Rule Management platform's versioned packs) already constructed
# above -- see rule_pack_resolution.py. They share
# evaluate_incident_use_case.orchestrator (not a second PipelineOrchestrator
# instance) so simulation is provably running identical pipeline
# configuration (including the SLA matrix lookup) to production, not a
# parallel approximation of it.
what_if_simulation_use_case = WhatIfSimulationUseCase(
    rule_repository, rule_pack_repository, orchestrator=evaluate_incident_use_case.orchestrator,
)
replay_simulation_use_case = ReplaySimulationUseCase(
    incident_repository, decision_repository, rule_repository, rule_pack_repository,
    orchestrator=evaluate_incident_use_case.orchestrator,
)
compare_rule_packs_use_case = CompareRulePacksUseCase(
    incident_repository, rule_repository, rule_pack_repository,
    orchestrator=evaluate_incident_use_case.orchestrator,
    max_incidents=settings.simulation_max_compare_incidents,
)

# Bulk evaluate needs two EvaluateIncidentUseCase instances that are
# otherwise identical to the real one above and differ only in whether a
# DecisionRepository is attached -- `persist=false` callers get the
# dry-run instance so nothing they submit is ever written, without
# BulkEvaluateUseCase having to reimplement any persistence-skipping logic
# itself (see bulk_evaluate.py's docstring).
_evaluate_incident_dry_run_use_case = EvaluateIncidentUseCase(
    rule_repository=rule_repository,
    orchestrator=evaluate_incident_use_case.orchestrator,
    context_aggregation_service=context_aggregation_service,
    decision_repository=None,
)
bulk_evaluate_use_case = BulkEvaluateUseCase(
    persisting_use_case=evaluate_incident_use_case,
    dry_run_use_case=_evaluate_incident_dry_run_use_case,
    max_items=settings.bulk_evaluate_max_items,
)
decision_distribution_use_case = DecisionDistributionUseCase(decision_repository)
