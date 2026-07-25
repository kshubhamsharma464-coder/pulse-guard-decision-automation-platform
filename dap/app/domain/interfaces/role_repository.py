from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.entities.role import Role


class RoleRepository(ABC):
    @abstractmethod
    def save(self, role: Role) -> Role: ...

    @abstractmethod
    def get_by_code(self, code: str) -> Optional[Role]: ...

    @abstractmethod
    def list_all(self) -> List[Role]: ...
