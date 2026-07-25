from app.infrastructure.external.base_stub_provider import StaticFieldProvider


class CompetitiveIntelProvider(StaticFieldProvider):
    """STUB for competitive intelligence (design doc §2)."""
    source_name = "competitive_intelligence"
    default_fields = {"competitorCampaignActiveInRegion": False}
