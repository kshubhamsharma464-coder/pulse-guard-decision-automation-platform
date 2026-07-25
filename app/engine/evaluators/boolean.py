from .base import Evaluator


class EqualsEvaluator(Evaluator):
    operator = "=="

    def evaluate(self, args, data, engine):
        left = engine.evaluate(args[0], data)
        right = engine.evaluate(args[1], data)
        return left == right


class NotEqualsEvaluator(Evaluator):
    """Added for the customer_sla_rules_telecom pack's "notEquals" operator
    (SLA-RULE-007's Platinum exclusion). Registered the same way as every
    other operator -- RuleEngine's dispatcher didn't need to change."""

    operator = "!="

    def evaluate(self, args, data, engine):
        left = engine.evaluate(args[0], data)
        right = engine.evaluate(args[1], data)
        return left != right
