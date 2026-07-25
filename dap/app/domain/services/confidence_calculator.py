class ConfidenceCalculator:
    """Data-completeness confidence -- fraction of context sources that returned
    live data vs. fell back to a default (design doc §6/§9 edge case 28). Deliberately
    NOT the same number as 'how strong is the rule consensus' (see architecture-review.md §3)."""

    def compute(self, total_context_sources: int, degraded_sources: int) -> float:
        if total_context_sources <= 0:
            return 100.0
        live = max(total_context_sources - degraded_sources, 0)
        return round(100.0 * live / total_context_sources, 2)
