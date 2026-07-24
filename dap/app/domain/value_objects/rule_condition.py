from dataclasses import dataclass
from typing import Any, Dict
from app.engine.evaluator_factory import RuleEngine

_ENGINE = RuleEngine()


@dataclass(frozen=True)
class RuleCondition:
    """Immutable wrapper around a JsonLogic-style condition tree, evaluated via the
    domain-agnostic engine. This is the seam between telecom-aware domain code and
    the reusable engine (design doc §10, cross-vertical reuse)."""

    tree: Dict[str, Any]

    def is_satisfied_by(self, data: Dict[str, Any]) -> bool:
        try:
            result = _ENGINE.evaluate(self.tree, data)
        except ValueError:
            return False
        return bool(result)

    def specificity(self) -> int:
        """Leaf-comparison count, used as a conflict-resolution tiebreak (design doc §3b)."""
        return _count_leaves(self.tree)


def _count_leaves(node: Any) -> int:
    if not isinstance(node, dict) or len(node) != 1:
        return 0
    operator, args = next(iter(node.items()))
    if operator in ("and", "or"):
        return sum(_count_leaves(child) for child in args)
    return 1
