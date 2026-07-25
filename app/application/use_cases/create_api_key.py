from datetime import datetime, timezone
from typing import List, Optional, Tuple
import uuid
from app.domain.entities.api_key import APIKey
from app.domain.interfaces.api_key_repository import APIKeyRepository
from app.core.security import generate_api_key, hash_api_key


class CreateApiKeyUseCase:
    """Returns (raw_key, APIKey) -- the raw key is only ever available at
    this moment; it's never stored or retrievable again (see api_key.py's
    docstring)."""

    def __init__(self, api_key_repository: APIKeyRepository):
        self.api_key_repository = api_key_repository

    def execute(self, owner_user_id: Optional[str], name: str, roles: Optional[List[str]] = None) -> Tuple[str, APIKey]:
        raw_key = generate_api_key()
        api_key = APIKey(
            id=str(uuid.uuid4()),
            key_prefix=raw_key[:12],
            hashed_key=hash_api_key(raw_key),
            owner_user_id=owner_user_id,
            name=name,
            roles=roles or ["viewer"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        saved = self.api_key_repository.save(api_key)
        return raw_key, saved
