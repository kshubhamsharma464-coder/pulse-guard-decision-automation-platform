"""Seeds default roles matching the permission catalog
(in_memory_permission_repository.py): admin (everything), operator
(day-to-day NOC work), viewer (read-only), plus two roles for the dynamic
Rule Management platform (docs/rule-management.md) -- editor (create/
modify draft rules and rule packs, cannot publish/activate/rollback/
delete) and policy_admin (exactly those four state-changing operations,
per the spec's "Only users with Policy Admin permission can Publish,
Rollback, Activate, Delete" / "Editors may Create, Modify Drafts, View").
New users default to "viewer" (see app/domain/entities/user.py) --
least privilege by default."""

from typing import Dict, List, Optional
from app.domain.interfaces.role_repository import RoleRepository
from app.domain.entities.role import Role

_ALL_PERMISSIONS = [
    "incidents:evaluate", "incidents:create", "incidents:read",
    "decisions:read", "decisions:override",
    "rules:manage", "rules:edit", "rules:read", "rules:publish", "rules:activate", "rules:rollback", "rules:delete",
    "escalations:acknowledge", "users:manage", "apikeys:manage",
    "simulation:run",
]

_DEFAULT_ROLES: List[Role] = [
    Role(code="admin", name="Administrator", permissions=list(_ALL_PERMISSIONS),
         description="Full access, including user/role management and rule-pack policy admin."),
    Role(code="operator", name="NOC Operator",
         permissions=["incidents:evaluate", "incidents:create", "incidents:read",
                      "decisions:read", "decisions:override", "escalations:acknowledge", "rules:read", "simulation:run"],
         description="Day-to-day incident handling."),
    Role(code="viewer", name="Viewer", permissions=["decisions:read", "rules:read", "incidents:read"],
         description="Read-only access. Default role for new users."),
    Role(code="editor", name="Rule Editor",
         permissions=["rules:edit", "rules:read", "simulation:run"],
         description="Create rules/rule packs and modify drafts; cannot publish, activate, roll back, or delete. Can run what-if simulations to test drafts before requesting publish."),
    Role(code="policy_admin", name="Policy Admin",
         permissions=["rules:edit", "rules:read", "rules:publish", "rules:activate", "rules:rollback", "rules:delete", "simulation:run"],
         description="Publish, activate, roll back, and delete rule packs -- the four state-changing operations the spec reserves for this role. Can also run simulations/comparisons as part of that review."),
]


class InMemoryRoleRepository(RoleRepository):
    def __init__(self):
        self._by_code: Dict[str, Role] = {r.code: r for r in _DEFAULT_ROLES}

    def save(self, role: Role) -> Role:
        self._by_code[role.code] = role
        return role

    def get_by_code(self, code: str) -> Optional[Role]:
        return self._by_code.get(code)

    def list_all(self) -> List[Role]:
        return list(self._by_code.values())
