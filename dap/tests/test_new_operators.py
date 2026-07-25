"""Isolated unit tests for the four JsonLogic operators added to support the
three externally-authored rule packs: != (SLA pack), * (SLA pack, dynamic
threshold formula), contains (vast pack), in_holiday_period (vast pack,
documented stub). Each is tested directly through RuleEngine, independent of
any rule pack, to pin down operator semantics regardless of what happens to
the packs that currently use them."""

from app.engine.evaluator_factory import RuleEngine

engine = RuleEngine()


def test_not_equals_true_and_false():
    assert engine.evaluate({"!=": [{"var": "tier"}, "Platinum"]}, {"tier": "Gold"}) is True
    assert engine.evaluate({"!=": [{"var": "tier"}, "Platinum"]}, {"tier": "Platinum"}) is False


def test_multiply_used_in_a_comparison():
    tree = {">=": [{"var": "minutesElapsed"}, {"*": [{"var": "slaResponseMinutes"}, 0.8]}]}
    assert engine.evaluate(tree, {"minutesElapsed": 40, "slaResponseMinutes": 50}) is True
    assert engine.evaluate(tree, {"minutesElapsed": 30, "slaResponseMinutes": 50}) is False


def test_contains_haystack_needle_convention():
    assert engine.evaluate({"contains": [{"var": "tags"}, "vip"]}, {"tags": ["vip", "gold"]}) is True
    assert engine.evaluate({"contains": [{"var": "tags"}, "vip"]}, {"tags": ["gold"]}) is False


def test_in_holiday_period_stub_reads_referenced_field_truthiness():
    """Documented stub: real calendar lookup would replace the evaluator body;
    for now it reflects the referenced field's own truthiness and ignores the
    literal `value` operand."""
    assert engine.evaluate({"in_holiday_period": [{"var": "isHoliday"}, True]}, {"isHoliday": True}) is True
    assert engine.evaluate({"in_holiday_period": [{"var": "isHoliday"}, True]}, {"isHoliday": False}) is False
