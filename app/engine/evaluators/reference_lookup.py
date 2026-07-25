from .base import Evaluator


class InHolidayPeriodEvaluator(Evaluator):
    """STUB, same honest pattern as the Context Aggregation Layer's provider
    stubs (app/infrastructure/external/). The customer_sla_rules_vast pack's
    CSR-024 condition is {"field": "request.date", "op": "in_holiday_period",
    "value": true} -- correctly answering "is this date a holiday" needs a
    real holiday-calendar reference data source we don't have. Rather than
    fake calendar logic, this evaluator honestly does the only thing
    possible without one: it reads whatever value the caller already put at
    the referenced field and returns its truthiness, ignoring the literal
    `value` operand (which is a marker in the source schema, not a real
    comparison target). Practically this means CSR-024 only fires today if
    the caller/context layer pre-computes holiday status and stores it under
    that same field name -- a real implementation would replace this class's
    body with an actual calendar lookup and keep the same "in_holiday_period"
    operator name, so no rule authored against this pack needs to change."""

    operator = "in_holiday_period"

    def evaluate(self, args, data, engine):
        value = engine.evaluate(args[0], data)
        return bool(value)
