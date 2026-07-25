from typing import List, Optional
from sqlalchemy.orm import sessionmaker
from app.domain.interfaces.permission_repository import PermissionRepository
from app.domain.entities.permission import Permission
from app.infrastructure.db.models import PermissionORM
from app.infrastructure.db.mappers import permission_to_domain, permission_to_orm


class PostgresPermissionRepository(PermissionRepository):
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def save(self, permission: Permission) -> Permission:
        with self._session_factory() as session:
            existing = session.query(PermissionORM).filter(PermissionORM.code == permission.code).one_or_none()
            if existing is not None:
                existing.description = permission.description
                session.commit()
                session.refresh(existing)
                return permission_to_domain(existing)
            row = permission_to_orm(permission)
            session.add(row)
            session.commit()
            session.refresh(row)
            return permission_to_domain(row)

    def get_by_code(self, code: str) -> Optional[Permission]:
        with self._session_factory() as session:
            row = session.query(PermissionORM).filter(PermissionORM.code == code).one_or_none()
            return permission_to_domain(row) if row else None

    def list_all(self) -> List[Permission]:
        with self._session_factory() as session:
            return [permission_to_domain(r) for r in session.query(PermissionORM).all()]
