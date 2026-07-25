from .base import Evaluator


class VarEvaluator(Evaluator):
    """Resolves {"var": "context.regionIncidentCount10Min"} style dotted lookups.
    Missing keys resolve to None rather than raising -- callers treat None as
    "rule not satisfied", matching design doc: missing field = rule_skipped_missing_field."""

    operator = "var"

    def evaluate(self, args, data, engine):
        path = args[0] if isinstance(args, list) else args
        if path is None or path == "":
            return data
        current = data
        for part in str(path).split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current


class AndEvaluator(Evaluator):
    operator = "and"

    def evaluate(self, args, data, engine):
        return all(bool(engine.evaluate(node, data)) for node in args)


class OrEvaluator(Evaluator):
    operator = "or"

    def evaluate(self, args, data, engine):
        return any(bool(engine.evaluate(node, data)) for node in args)
