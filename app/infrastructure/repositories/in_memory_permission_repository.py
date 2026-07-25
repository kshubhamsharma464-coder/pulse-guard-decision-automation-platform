"""Seeds the permission catalog used by every default role
(in_memory_role_repository.py) and every `require_permission(...)` check
in the API layer. Adding a new protected capability means adding its code
here first -- RoleRepository implementations are expected to validate
role.permissions against this catalog on save."""

from typing import Dict, List, Optional
from app.domain.interfaces.permission_repository import PermissionRepository
from app.domain.entities.permission import Permission

_DEFAULT_PERMISSIONS: List[Permission] = [
    Permission(code="incidents:evaluate", description="Submit incidents for decisioning"),
    Permission(code="incidents:create", description="Create/persist an incident via POST /api/v1/incidents (with or without immediate evaluation)"),
    Permission(code="incidents:read", description="List/read persisted incidents"),
    Permission(code="decisions:read", description="Read past decisions and their explainability trace"),
    Permission(code="decisions:override", description="Manually override a decision"),
    Permission(code="rules:manage", description="Validate, activate, and roll back rule packs (legacy -- superseded by the rules:* set below for the dynamic Rule Management platform)"),
    Permission(code="escalations:acknowledge", description="Acknowledge an escalation event"),
    Permission(code="users:manage", description="Create/deactivate users and assign roles"),
    Permission(code="apikeys:manage", description="Create and revoke API keys"),
    # -- Dynamic Rule Management platform (docs/rule-management.md) --
    # "Editor" tier: create rules/rule packs, modify drafts, read.
    Permission(code="rules:edit", description="Create rules and rule packs, edit drafts, import/export JSON"),
    Permission(code="rules:read", description="List/read rules and rule packs"),
    # "Policy Admin" tier: the four state-changing/destructive operations.
    Permission(code="rules:publish", description="Publish a draft rule pack"),
    Permission(code="rules:activate", description="Activate a published (or rollback-target deprecated) rule pack version"),
    Permission(code="rules:rollback", description="Roll back the active rule pack to a prior version"),
    Permission(code="rules:delete", description="Soft-delete (archive) a rule pack"),
    # -- Simulation + bulk evaluation (Phase 4) --
    Permission(code="simulation:run", description="Run what-if simulations, historical replay, and rule-pack comparisons -- never persists anything"),
]


class InMemoryPermissionRepository(PermissionRepository):
    def __init__(self):
        self._by_code: Dict[str, Permission] = {p.code: p for p in _DEFAULT_PERMISSIONS}

    def save(self, permission: Permission) -> Permission:
        self._by_code[permission.code] = permission
        return permission

    def get_by_code(self, code: str) -> Optional[Permission]:
        return self._by_code.get(code)

    def list_all(self) -> List[Permission]:
        return list(self._by_code.values())
