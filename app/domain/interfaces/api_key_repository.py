from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.entities.api_key import APIKey


class APIKeyRepository(ABC):
    @abstractmethod
    def save(self, api_key: APIKey) -> APIKey: ...

    @abstractmethod
    def get_by_id(self, key_id: str) -> Optional[APIKey]: ...

    @abstractmethod
    def get_by_prefix(self, key_prefix: str) -> Optional[APIKey]: ...

    @abstractmethod
    def list_by_owner(self, owner_user_id: str) -> List[APIKey]: ...

    @abstractmethod
    def revoke(self, key_id: str) -> Optional[APIKey]: ...
