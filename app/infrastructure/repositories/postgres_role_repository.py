from typing import List, Optional
from sqlalchemy.orm import sessionmaker
from app.domain.interfaces.role_repository import RoleRepository
from app.domain.entities.role import Role
from app.infrastructure.db.models import RoleORM
from app.infrastructure.db.mappers import role_to_domain, role_to_orm


class PostgresRoleRepository(RoleRepository):
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def save(self, role: Role) -> Role:
        with self._session_factory() as session:
            existing = session.query(RoleORM).filter(RoleORM.code == role.code).one_or_none()
            if existing is not None:
                existing.name = role.name
                existing.permissions = list(role.permissions or [])
                existing.description = role.description
                session.commit()
                session.refresh(existing)
                return role_to_domain(existing)
            row = role_to_orm(role)
            session.add(row)
            session.commit()
            session.refresh(row)
            return role_to_domain(row)

    def get_by_code(self, code: str) -> Optional[Role]:
        with self._session_factory() as session:
            row = session.query(RoleORM).filter(RoleORM.code == code).one_or_none()
            return role_to_domain(row) if row else None

    def list_all(self) -> List[Role]:
        with self._session_factory() as session:
            return [role_to_domain(r) for r in session.query(RoleORM).all()]
