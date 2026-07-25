from datetime import datetime, timezone
from typing import List, Optional
import uuid
from app.domain.entities.user import User
from app.domain.interfaces.user_repository import UserRepository
from app.domain.interfaces.role_repository import RoleRepository
from app.core.security import hash_password


class RegisterUserUseCase:
    """New users default to the least-privileged "viewer" role (design
    intent, not just a field default -- enforced here so a caller can't
    silently self-elevate by passing an unknown role code)."""

    def __init__(self, user_repository: UserRepository, role_repository: RoleRepository):
        self.user_repository = user_repository
        self.role_repository = role_repository

    def execute(self, email: str, password: str, full_name: str = "", roles: Optional[List[str]] = None) -> User:
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            raise ValueError("A valid email address is required")
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        if self.user_repository.get_by_email(email) is not None:
            raise ValueError(f"A user with email '{email}' already exists")

        requested_roles = roles or ["viewer"]
        for code in requested_roles:
            if self.role_repository.get_by_code(code) is None:
                raise ValueError(f"Unknown role code: '{code}'")

        user = User(
            id=str(uuid.uuid4()),
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            roles=requested_roles,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        return self.user_repository.save(user)
