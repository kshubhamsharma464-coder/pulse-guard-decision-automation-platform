from abc import ABC, abstractmethod
from typing import Any, Dict


class Evaluator(ABC):
    """A single JsonLogic-style operator handler. New operators are added by
    writing a new Evaluator and registering it in evaluator_factory.py's
    default_registry() -- the RuleEngine dispatcher never changes (Open/Closed)."""

    operator: str

    @abstractmethod
    def evaluate(self, args: Any, data: Dict[str, Any], engine: "RuleEngine") -> Any:
        ...
