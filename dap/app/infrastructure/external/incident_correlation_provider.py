from app.infrastructure.external.base_stub_provider import StaticFieldProvider


class IncidentCorrelationProvider(StaticFieldProvider):
    """STUB for incident correlation state (design doc §2)."""
    source_name = "incident_correlation_state"
    default_fields = {
        "activeParentIncidentOnSameAsset": False,
        "upstreamDependencyAlreadyResolved": False,
        "duplicateOfExistingMajorIncident": False,
        "regionIncidentCount10Min": 0,
        "regionIncidentCount7Days": 0,
    }
