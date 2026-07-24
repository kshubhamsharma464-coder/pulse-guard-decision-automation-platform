from abc import ABC, abstractmethod
from typing import Optional
from app.domain.entities.rule_pack import RulePack


class RuleRepository(ABC):
    @abstractmethod
    def get_active(self, region: Optional[str] = None, tenant: Optional[str] = None) -> RulePack:
        ...
