from .base import Evaluator


class InEvaluator(Evaluator):
    """{"in": [{"var": "assetTier"}, ["Core Router", "5G Core"]]} -- list membership.
    Convention: [needle, haystack]."""
    operator = "in"

    def evaluate(self, args, data, engine):
        needle = engine.evaluate(args[0], data)
        haystack = engine.evaluate(args[1], data)
        if needle is None or haystack is None:
            return False
        try:
            return needle in haystack
        except TypeError:
            return False


class ContainsEvaluator(Evaluator):
    """{"contains": [{"var": "customer.tags"}, "vip"]} -- the reverse convention
    from InEvaluator: [haystack, needle]. Added for the customer_sla_rules_vast
    pack, which uses "contains" for both list membership (customer.tags) and
    substring matching (request.title) -- Python's `in` operator already
    handles both cases identically, so one evaluator covers both."""
    operator = "contains"

    def evaluate(self, args, data, engine):
        haystack = engine.evaluate(args[0], data)
        needle = engine.evaluate(args[1], data)
        if haystack is None or needle is None:
            return False
        try:
            return needle in haystack
        except TypeError:
            return False
