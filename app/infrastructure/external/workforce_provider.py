from app.infrastructure.external.base_stub_provider import StaticFieldProvider


class WorkforceProvider(StaticFieldProvider):
    """STUB for the dispatch/workforce system (design doc §2)."""
    source_name = "dispatch_workforce_system"
    default_fields = {"engineerCapacityAvailable": True}
