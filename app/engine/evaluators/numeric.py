from .base import Evaluator


class _Comparison(Evaluator):
    def compare(self, a, b) -> bool:
        raise NotImplementedError

    def evaluate(self, args, data, engine):
        left = engine.evaluate(args[0], data)
        right = engine.evaluate(args[1], data)
        if left is None or right is None:
            return False
        try:
            return self.compare(left, right)
        except TypeError:
            return False


class GreaterThanEvaluator(_Comparison):
    operator = ">"
    def compare(self, a, b): return a > b


class LessThanEvaluator(_Comparison):
    operator = "<"
    def compare(self, a, b): return a < b


class GreaterOrEqualEvaluator(_Comparison):
    operator = ">="
    def compare(self, a, b): return a >= b


class LessOrEqualEvaluator(_Comparison):
    operator = "<="
    def compare(self, a, b): return a <= b
