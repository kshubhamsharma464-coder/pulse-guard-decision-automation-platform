from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.entities.permission import Permission


class PermissionRepository(ABC):
    @abstractmethod
    def save(self, permission: Permission) -> Permission: ...

    @abstractmethod
    def get_by_code(self, code: str) -> Optional[Permission]: ...

    @abstractmethod
    def list_all(self) -> List[Permission]: ...
