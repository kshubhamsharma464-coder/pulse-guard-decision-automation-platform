from app.infrastructure.external.base_stub_provider import StaticFieldProvider


class CrmProvider(StaticFieldProvider):
    """STUB for the customer CRM (design doc §2)."""
    source_name = "customer_crm"
    default_fields = {"customerSegment": None, "regulatedSectorCustomerAffected": False}
