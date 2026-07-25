from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from app.interfaces.api import (
    incident_router, decision_router, health_router, auth_router, rule_pack_router, rule_router, ai_router,
    simulation_router,
)
from app.interfaces.api.lifespan import lifespan
from app.interfaces.api.middleware.security_headers import SecurityHeadersMiddleware
from app.interfaces.api.middleware.rate_limit import RateLimitMiddleware
from app.domain.exceptions import ConcurrentModificationError

tags_metadata = [
    {"name": "Incidents", "description": "Submit a network incident for automated decisioning (creates a decision)."},
    {"name": "Decisions", "description": "Retrieve past decisions and their full explainability trace (read-only), plus aggregate distribution and bulk evaluation (Phase 4)."},
    {"name": "Health", "description": "Liveness check."},
    {"name": "Auth", "description": "Registration, login, token refresh, and JWT-based RBAC (Phase 2). Optional -- see Settings.auth_required."},
    # "Rule Packs" and "Simulation" temporarily hidden from Swagger for the demo (see
    # include_in_schema=False below on their routers) -- routes are still fully live,
    # just not listed. Re-enable by uncommenting these two entries and removing
    # include_in_schema=False from the matching app.include_router(...) calls.
    # {"name": "Rule Packs", "description": "Rule pack lifecycle: create/import/export, publish, activate, rollback, soft delete (Phase 2.5 dynamic Rule Management platform). See docs/rule-management.md."},
    {"name": "Rules", "description": "Individual-rule CRUD within a Draft rule pack, plus validation and change history (Phase 2.5)."},
    {"name": "AI", "description": "AI-assisted, non-authoritative: natural-language rule drafting, rule documentation, decision narration. AI never makes or alters a business decision -- see docs/ai-assist.md."},
    # {"name": "Simulation", "description": "What-if analysis, historical replay, and rule-version comparison -- all read-only, never persist a decision (Phase 4). See docs/simulation.md."},
]

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    openapi_schema.setdefault("components", {})
    openapi_schema["components"].setdefault("securitySchemes", {})
    openapi_schema["components"]["securitySchemes"]["bearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    for path_item in openapi_schema.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation.setdefault("security", [{"bearerAuth": []}])
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app = FastAPI(
    title="Pulse Guard",
    description=(
        "**Telecom Network Incident Decision Automation Platform** Converts raw "
        "network telemetry into governed, explainable, auditable operational "
        "decisions -- priority, dispatch, reroute, notifications, execution plan "
        "-- through versioned, runtime-configurable business rules rather than "
        "hardcoded thresholds.\n\n"
        "35 seeded rules across 9 families (safety/regulatory, network impact, "
        "customer value, temporal, operational feasibility, repetition/escalation, "
        "suppression, competitive resilience, compliance) are evaluated, conflict-"
        "resolved, and turned into an ordered execution plan on every request.\n\n"
        "See `docs/decision-engine-design.md` for the full rule-base design and "
        "`docs/tradeoffs.md` for the architecture decision record."
    ),
    version="0.1.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
    # persistAuthorization: once you click Authorize and paste a bearer token,
    # Swagger UI keeps using it for every endpoint and remembers it across page
    # reloads (stored in the browser) -- no need to re-enter it per request or
    # per refresh.
    swagger_ui_parameters={"persistAuthorization": True},
)

# Order matters: Starlette runs middleware in reverse registration order,
# so RateLimitMiddleware (added last) runs first, rejecting over-limit
# requests before SecurityHeadersMiddleware does any work on them. Both
# are no-ops unless explicitly configured -- see their own docstrings.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.openapi = custom_openapi


@app.exception_handler(ConcurrentModificationError)
async def concurrent_modification_handler(request: Request, exc: ConcurrentModificationError):
    """Phase 5 (docs/policy-platform.md, "Concurrency"): translates a
    PostgreSQL optimistic-locking conflict (RuleSetORM.lock_version,
    raised as this framework-independent domain exception by
    PostgresRulePackRepository) into 409 Conflict, globally, for every
    route -- so no individual router function needs its own
    except-ConcurrentModificationError block. A 409 here means "someone
    else changed this rule pack between your read and your write, reload
    and retry" -- distinct from the 400s the rest of this API returns for
    invalid input."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})

app.include_router(incident_router.router)
app.include_router(decision_router.router)
app.include_router(health_router.router)
app.include_router(auth_router.router)
# include_in_schema=False: hidden from Swagger for now (routes are still
# fully live/functional, just not listed in /docs) -- see the commented-out
# tags_metadata entries above. Drop include_in_schema=False to bring them
# back into Swagger later.
app.include_router(rule_pack_router.router, include_in_schema=False)
app.include_router(rule_router.router)
app.include_router(ai_router.router)
app.include_router(simulation_router.simulation_router, include_in_schema=False)
app.include_router(simulation_router.bulk_evaluate_router)
