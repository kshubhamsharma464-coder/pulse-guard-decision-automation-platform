from typing import Any, Dict
from app.engine.evaluators.base import Evaluator
from app.engine.evaluators.composite import VarEvaluator, AndEvaluator, OrEvaluator
from app.engine.evaluators.numeric import (
    GreaterThanEvaluator, LessThanEvaluator, GreaterOrEqualEvaluator, LessOrEqualEvaluator,
)
from app.engine.evaluators.boolean import EqualsEvaluator, NotEqualsEvaluator
from app.engine.evaluators.membership import InEvaluator, ContainsEvaluator
from app.engine.evaluators.arithmetic import MultiplyEvaluator
from app.engine.evaluators.reference_lookup import InHolidayPeriodEvaluator


class PluginRegistry:
    """Operator registry -- new operators register here without touching RuleEngine."""

    def __init__(self):
        self._evaluators: Dict[str, Evaluator] = {}

    def register(self, evaluator: Evaluator) -> None:
        self._evaluators[evaluator.operator] = evaluator

    def get(self, operator: str) -> Evaluator:
        if operator not in self._evaluators:
            raise ValueError(f"No evaluator registered for operator '{operator}'")
        return self._evaluators[operator]


def default_registry() -> PluginRegistry:
    registry = PluginRegistry()
    for cls in (
        VarEvaluator, AndEvaluator, OrEvaluator,
        GreaterThanEvaluator, LessThanEvaluator, GreaterOrEqualEvaluator, LessOrEqualEvaluator,
        EqualsEvaluator, NotEqualsEvaluator, InEvaluator, MultiplyEvaluator,
        ContainsEvaluator, InHolidayPeriodEvaluator,
    ):
        registry.register(cls())
    return registry


class RuleEngine:
    """Domain-agnostic JsonLogic-style evaluator. Must never import from app.domain --
    that boundary is what makes the rule pack swappable across verticals (design doc §10)."""

    def __init__(self, registry: PluginRegistry = None):
        self.registry = registry or default_registry()

    def evaluate(self, node: Any, data: Dict[str, Any]) -> Any:
        if not isinstance(node, dict):
            return node
        if len(node) != 1:
            raise ValueError(f"Malformed condition node: {node!r}")
        operator, args = next(iter(node.items()))
        evaluator = self.registry.get(operator)
        return evaluator.evaluate(args, data, self)
