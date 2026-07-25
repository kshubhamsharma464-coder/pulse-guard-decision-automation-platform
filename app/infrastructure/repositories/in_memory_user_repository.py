from typing import Dict, List, Optional
from app.domain.interfaces.user_repository import UserRepository
from app.domain.entities.user import User


class InMemoryUserRepository(UserRepository):
    def __init__(self):
        self._by_id: Dict[str, User] = {}
        self._by_email: Dict[str, str] = {}  # email (lowercased) -> user id

    def save(self, user: User) -> User:
        self._by_id[user.id] = user
        self._by_email[user.email.lower()] = user.id
        return user

    def get_by_id(self, user_id: str) -> Optional[User]:
        return self._by_id.get(user_id)

    def get_by_email(self, email: str) -> Optional[User]:
        user_id = self._by_email.get(email.lower())
        return self._by_id.get(user_id) if user_id else None

    def list_all(self) -> List[User]:
        return list(self._by_id.values())
