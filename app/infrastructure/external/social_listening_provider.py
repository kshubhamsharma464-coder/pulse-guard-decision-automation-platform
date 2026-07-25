from app.infrastructure.external.base_stub_provider import StaticFieldProvider


class SocialListeningProvider(StaticFieldProvider):
    """STUB for social listening (design doc §2)."""
    source_name = "social_listening"
    default_fields = {"negativeSocialMentionSpike": False}
