from typing import Any, Dict, List, Tuple
from app.domain.entities.rule import Rule

_SEVERITY_ORDER = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}
_MODIFIER_FIELDS = ("priorityFloor", "priorityBumpOneLevel")


class ConflictResolver:
    """Design doc §3b: suppressor pass -> conflict-group pass -> field merge.

    NOTE (known simplification): a rule's `conflict_group` tag is rule-level, not
    per-field. For our seeded rule base this never produces a wrong answer because
    rules sharing a field either genuinely share one conflict_group or their values
    happen to agree when they don't -- but a rule that wrote two independently
    contested fields under one conflict_group tag would need a per-field tag to be
    fully correct. Flagged here rather than silently relied on."""

    def resolve(self, matched: List[Rule]) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
        suppressed: List[Dict[str, Any]] = []

        field_writers: Dict[str, List[Rule]] = {}
        for rule in matched:
            for field_name in rule.actions:
                if field_name in _MODIFIER_FIELDS:
                    continue
                field_writers.setdefault(field_name, []).append(rule)

        actions: Dict[str, Any] = {}
        for field_name, writers in field_writers.items():
            effective = self._apply_suppression(field_name, writers, suppressed)
            if not effective:
                continue
            if len(effective) == 1:
                actions[field_name] = effective[0].actions[field_name]
                continue

            values = [r.actions[field_name] for r in effective]
            if all(v == values[0] for v in values):
                # Rules agree on this field's value -- nothing to resolve, and
                # nobody should be logged as "suppressed" for agreeing (this is
                # the fix for the conflict_group-is-rule-level-not-per-field
                # simplification noted in the class docstring: two rules can
                # share a conflict_group because they compete on *priority*
                # while both incidentally also writing the *same* value to an
                # unrelated field like customerNotification).
                actions[field_name] = values[0]
                continue

            groups = {r.conflict_group for r in effective}
            if len(groups) == 1 and None not in groups:
                winner = self._resolve_conflict_group(effective, field_name, suppressed)
                actions[field_name] = winner.actions[field_name]
            else:
                actions[field_name] = self._merge_field(field_name, effective)

        actions = self._apply_priority_postprocessing(actions, matched)
        mitigations = self._merge_mitigations(matched)
        return actions, mitigations, suppressed

    def _apply_suppression(self, field_name: str, writers: List[Rule], suppressed: List[Dict[str, Any]]) -> List[Rule]:
        suppressors = [r for r in writers if r.is_suppressor]
        if not suppressors:
            return writers

        non_suppressible = [r for r in writers if r.non_suppressible]
        if non_suppressible:
            for s in suppressors:
                suppressed.append({
                    "rule_code": s.rule_code, "field": field_name,
                    "reason": "attempted suppression overridden by non-suppressible rule",
                })
            return [r for r in writers if not r.is_suppressor]

        winner = max(suppressors, key=lambda r: r.priority_weight)
        for r in writers:
            if r is not winner:
                suppressed.append({"rule_code": r.rule_code, "field": field_name, "reason": f"suppressed by {winner.rule_code}"})
        return [winner]

    def _resolve_conflict_group(self, candidates: List[Rule], field_name: str, suppressed: List[Dict[str, Any]]) -> Rule:
        max_weight = max(r.priority_weight for r in candidates)
        top = [r for r in candidates if r.priority_weight == max_weight]
        if len(top) > 1:
            max_spec = max(r.conditions.specificity() for r in top)
            top = [r for r in top if r.conditions.specificity() == max_spec]
        winner = sorted(top, key=lambda r: r.rule_code)[0]
        for r in candidates:
            if r is not winner:
                suppressed.append({"rule_code": r.rule_code, "field": field_name, "reason": f"lost conflict group to {winner.rule_code}"})
        return winner

    def _merge_field(self, field_name: str, candidates: List[Rule]) -> Any:
        values = [r.actions[field_name] for r in candidates]
        if field_name == "priority":
            return max(values, key=lambda v: _SEVERITY_ORDER.get(v, -1))
        if field_name in ("targetSLA", "slaTarget"):
            return min(values, key=_parse_duration_minutes)
        if all(isinstance(v, bool) for v in values):
            return any(values)
        best = max(candidates, key=lambda r: r.priority_weight)
        return best.actions[field_name]

    def _apply_priority_postprocessing(self, actions: Dict[str, Any], matched: List[Rule]) -> Dict[str, Any]:
        order = ["Low", "Medium", "High", "Critical"]
        floors = [r.actions["priorityFloor"] for r in matched if "priorityFloor" in r.actions]
        bumps = sum(1 for r in matched if r.actions.get("priorityBumpOneLevel"))
        current = actions.get("priority")
        if current is None and floors:
            current = "Low"
        if current is not None:
            if floors:
                floor_idx = max(order.index(f) for f in floors if f in order)
                if order.index(current) < floor_idx:
                    current = order[floor_idx]
            if bumps:
                idx = min(order.index(current) + bumps, len(order) - 1)
                current = order[idx]
            actions["priority"] = current
        return actions

    def _merge_mitigations(self, matched: List[Rule]) -> Dict[str, Any]:
        mitigations: Dict[str, Any] = {}
        for rule in matched:
            for k, v in rule.mitigations.items():
                if isinstance(v, bool):
                    mitigations[k] = mitigations.get(k, False) or v
                else:
                    mitigations.setdefault(k, v)
        return mitigations


def _parse_duration_minutes(value: str) -> int:
    parts = value.lower().split()
    n = int(parts[0])
    return n * 60 if "hour" in value.lower() else n
