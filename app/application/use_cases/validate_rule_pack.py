from dataclasses import dataclass, field
from typing import List
from app.domain.entities.rule_pack import RulePack


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)


class ValidateRulePackUseCase:
    """Design doc §8 step 3: structural check + a static conflictsWith
    contradiction check, run before a draft can be promoted to shadow."""

    def execute(self, pack: RulePack) -> ValidationResult:
        errors: List[str] = []

        if not pack.rules:
            errors.append("Rule pack has zero rules -- cannot activate an empty pack")

        codes = {r.rule_code for r in pack.rules}
        by_code = {r.rule_code: r for r in pack.rules}

        for rule in pack.rules:
            try:
                rule.conditions.specificity()
            except Exception as exc:
                errors.append(f"{rule.rule_code} has a malformed conditions tree: {exc}")

            for other_code in rule.conflicts_with:
                if other_code not in codes:
                    errors.append(
                        f"{rule.rule_code} declares conflictsWith '{other_code}', "
                        f"which does not exist in this rule pack"
                    )
                    continue
                other = by_code[other_code]
                shares_group = rule.conflict_group and other.conflict_group == rule.conflict_group
                either_resolves_it = rule.non_suppressible or other.non_suppressible or rule.is_suppressor or other.is_suppressor
                if shares_group and not either_resolves_it:
                    errors.append(
                        f"{rule.rule_code} and {other_code} share conflict_group "
                        f"'{rule.conflict_group}' and are declared as conflicting, but "
                        f"neither is a suppressor nor non_suppressible -- resolution "
                        f"would fall through to an unexplained weight/specificity tiebreak"
                    )

        return ValidationResult(is_valid=not errors, errors=errors)
