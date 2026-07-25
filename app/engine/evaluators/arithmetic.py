from .base import Evaluator


class MultiplyEvaluator(Evaluator):
    """Added for the customer_sla_rules_telecom pack's dynamic-threshold
    condition (SLA-RULE-004: "slaResponseMinutes * 0.8"). Comparison
    evaluators (numeric.py) already recursively evaluate both operands, so
    nesting {"*": [...]} as a comparison's right-hand side works with no
    changes anywhere else -- this is the Open/Closed claim in tradeoffs.md
    #7 actually being exercised, not just asserted."""

    operator = "*"

    def evaluate(self, args, data, engine):
        left = engine.evaluate(args[0], data)
        right = engine.evaluate(args[1], data)
        if left is None or right is None:
            return None
        return left * right
