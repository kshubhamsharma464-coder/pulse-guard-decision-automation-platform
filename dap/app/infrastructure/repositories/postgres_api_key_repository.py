from typing import List, Optional
from sqlalchemy.orm import sessionmaker
from app.domain.interfaces.api_key_repository import APIKeyRepository
from app.domain.entities.api_key import APIKey
from app.infrastructure.db.models import APIKeyORM
from app.infrastructure.db.mappers import api_key_to_domain, api_key_to_orm


class PostgresAPIKeyRepository(APIKeyRepository):
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def save(self, api_key: APIKey) -> APIKey:
        with self._session_factory() as session:
            existing = session.get(APIKeyORM, api_key.id) if api_key.id else None
            if existing is not None:
                existing.is_active = api_key.is_active
                existing.last_used_at = api_key.last_used_at
                existing.name = api_key.name
                existing.roles = list(api_key.roles or [])
                session.commit()
                session.refresh(existing)
                return api_key_to_domain(existing)
            row = api_key_to_orm(api_key)
            session.add(row)
            session.commit()
            session.refresh(row)
            return api_key_to_domain(row)

    def get_by_id(self, key_id: str) -> Optional[APIKey]:
        with self._session_factory() as session:
            row = session.get(APIKeyORM, key_id)
            return api_key_to_domain(row) if row else None

    def get_by_prefix(self, key_prefix: str) -> Optional[APIKey]:
        with self._session_factory() as session:
            row = session.query(APIKeyORM).filter(APIKeyORM.key_prefix == key_prefix).one_or_none()
            return api_key_to_domain(row) if row else None

    def list_by_owner(self, owner_user_id: str) -> List[APIKey]:
        with self._session_factory() as session:
            rows = session.query(APIKeyORM).filter(APIKeyORM.owner_user_id == owner_user_id).all()
            return [api_key_to_domain(r) for r in rows]

    def revoke(self, key_id: str) -> Optional[APIKey]:
        with self._session_factory() as session:
            row = session.get(APIKeyORM, key_id)
            if row is None:
                return None
            row.is_active = False
            session.commit()
            session.refresh(row)
            return api_key_to_domain(row)
