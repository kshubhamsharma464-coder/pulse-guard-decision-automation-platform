from app.infrastructure.external.base_stub_provider import StaticFieldProvider


class HistoricalContextProvider(StaticFieldProvider):
    """STUB for the historical incident store (design doc §2)."""
    source_name = "historical_incident_store"
    default_fields = {
        "repairVisitCount90Days": 0,
        "warrantyExpired": False,
        "towerFlapCount1Hour": 0,
        "sameVendorFaultAssetCount24h": 0,
        "correlatedFaultTypesAtSite": 0,
    }
