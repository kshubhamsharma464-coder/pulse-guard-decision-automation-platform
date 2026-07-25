from app.infrastructure.external.base_stub_provider import StaticFieldProvider


class VendorKnowledgeBaseProvider(StaticFieldProvider):
    """STUB for the vendor knowledge base (design doc §2)."""
    source_name = "vendor_knowledge_base"
    default_fields = {"knownFirmwareBugMatch": False, "remoteFixAvailable": False}
