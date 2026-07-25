"""One-time seed: populate permissions + roles with the same defaults
InMemoryPermissionRepository/InMemoryRoleRepository ship with, so a fresh
Postgres deployment has a usable RBAC catalog immediately. Run after
`alembic upgrade head`:

    python3 scripts/seed_default_roles_permissions.py

Does NOT create any users -- there is deliberately no default admin
account seeded into the database (a hardcoded default credential is a
real security liability). Create the first admin via:

    POST /api/v1/auth/register  {"email": ..., "password": ..., "roles": ["admin"]}

then, if auth_required is later turned on, promote/demote roles through
whatever admin tooling exists at that point (role assignment via API is
intentionally out of scope for this phase -- see docs/auth.md).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.settings import get_settings
from app.infrastructure.db.session import get_engine, get_sessionmaker
from app.infrastructure.repositories.in_memory_permission_repository import _DEFAULT_PERMISSIONS
from app.infrastructure.repositories.in_memory_role_repository import _DEFAULT_ROLES
from app.infrastructure.db.mappers import permission_to_orm, role_to_orm
from app.infrastructure.db.models import PermissionORM, RoleORM


def main() -> None:
    settings = get_settings()
    engine = get_engine(settings.database_url)
    session_factory = get_sessionmaker(engine)

    with session_factory() as session:
        existing_perms = {row.code for row in session.query(PermissionORM).all()}
        added_perms = 0
        for permission in _DEFAULT_PERMISSIONS:
            if permission.code in existing_perms:
                print(f"  skip permission {permission.code} (already seeded)")
                continue
            session.add(permission_to_orm(permission))
            added_perms += 1
            print(f"  seeded permission: {permission.code}")

        existing_roles = {row.code for row in session.query(RoleORM).all()}
        added_roles = 0
        for role in _DEFAULT_ROLES:
            if role.code in existing_roles:
                print(f"  skip role {role.code} (already seeded)")
                continue
            session.add(role_to_orm(role))
            added_roles += 1
            print(f"  seeded role: {role.code} -> {role.permissions}")

        session.commit()
    print(f"done -- {added_perms} permission(s), {added_roles} role(s) added")


if __name__ == "__main__":
    main()
