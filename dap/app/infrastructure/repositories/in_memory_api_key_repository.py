from typing import Dict, List, Optional
from app.domain.interfaces.api_key_repository import APIKeyRepository
from app.domain.entities.api_key import APIKey


class InMemoryAPIKeyRepository(APIKeyRepository):
    def __init__(self):
        self._by_id: Dict[str, APIKey] = {}
        self._by_prefix: Dict[str, str] = {}  # key_prefix -> key id

    def save(self, api_key: APIKey) -> APIKey:
        self._by_id[api_key.id] = api_key
        self._by_prefix[api_key.key_prefix] = api_key.id
        return api_key

    def get_by_id(self, key_id: str) -> Optional[APIKey]:
        return self._by_id.get(key_id)

    def get_by_prefix(self, key_prefix: str) -> Optional[APIKey]:
        key_id = self._by_prefix.get(key_prefix)
        return self._by_id.get(key_id) if key_id else None

    def list_by_owner(self, owner_user_id: str) -> List[APIKey]:
        return [k for k in self._by_id.values() if k.owner_user_id == owner_user_id]

    def revoke(self, key_id: str) -> Optional[APIKey]:
        key = self._by_id.get(key_id)
        if key is not None:
            key.is_active = False
        return key
