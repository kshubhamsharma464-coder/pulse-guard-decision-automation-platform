from app.infrastructure.external.base_stub_provider import StaticFieldProvider


class RegionalPolicyProvider(StaticFieldProvider):
    """STUB for the regional policy store (design doc §2)."""
    source_name = "regional_policy_store"
    default_fields = {
        "isPeakHoursLocal": False,
        "isOffHoursOrHoliday": False,
        "highRiskZone": False,
        "gdprScopeRegion": False,
    }
