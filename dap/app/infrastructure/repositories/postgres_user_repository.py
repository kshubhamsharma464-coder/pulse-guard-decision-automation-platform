from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import sessionmaker
from app.domain.interfaces.user_repository import UserRepository
from app.domain.entities.user import User
from app.infrastructure.db.models import UserORM
from app.infrastructure.db.mappers import user_to_domain, user_to_orm


class PostgresUserRepository(UserRepository):
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def save(self, user: User) -> User:
        with self._session_factory() as session:
            existing = session.get(UserORM, user.id) if user.id else None
            if existing is not None:
                existing.email = user.email
                existing.hashed_password = user.hashed_password
                existing.full_name = user.full_name
                existing.roles = list(user.roles or [])
                existing.is_active = user.is_active
                existing.last_login_at = user.last_login_at
                session.commit()
                session.refresh(existing)
                return user_to_domain(existing)
            row = user_to_orm(user)
            session.add(row)
            session.commit()
            session.refresh(row)
            return user_to_domain(row)

    def get_by_id(self, user_id: str) -> Optional[User]:
        with self._session_factory() as session:
            row = session.get(UserORM, user_id)
            return user_to_domain(row) if row else None

    def get_by_email(self, email: str) -> Optional[User]:
        # Case-insensitive on both sides -- matches InMemoryUserRepository's
        # behavior even if a row was inserted with mixed-case email (the
        # normal path, RegisterUserUseCase, always lowercases first).
        with self._session_factory() as session:
            row = session.query(UserORM).filter(func.lower(UserORM.email) == email.lower()).one_or_none()
            return user_to_domain(row) if row else None

    def list_all(self) -> List[User]:
        with self._session_factory() as session:
            return [user_to_domain(r) for r in session.query(UserORM).all()]
