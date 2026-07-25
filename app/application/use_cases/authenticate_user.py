from datetime import datetime, timezone
from app.domain.entities.user import User
from app.domain.interfaces.user_repository import UserRepository
from app.core.security import verify_password


class AuthenticateUserUseCase:
    """Deliberately returns the same error for "no such user" and "wrong
    password" -- distinguishing them lets an attacker enumerate valid
    email addresses."""

    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    def execute(self, email: str, password: str) -> User:
        user = self.user_repository.get_by_email((email or "").strip().lower())
        if user is None or not verify_password(password, user.hashed_password):
            raise ValueError("Invalid email or password")
        if not user.is_active:
            raise ValueError("This account has been deactivated")
        user.last_login_at = datetime.now(timezone.utc)
        return self.user_repository.save(user)
