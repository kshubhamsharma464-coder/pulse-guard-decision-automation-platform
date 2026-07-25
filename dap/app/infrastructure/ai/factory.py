"""Factory pattern: Settings.ai_provider -> concrete AIProvider instance.
The only place that branches on the provider type -- every use case and
router depends on the AIProvider interface, constructed once here and
imported from app/interfaces/api/dependencies.py, same composition-root
convention as every other pluggable component in this codebase."""

from app.core.settings import Settings
from app.domain.interfaces.ai_provider import AIProvider
from app.infrastructure.ai.stub_ai_provider import StubAIProvider
from app.infrastructure.ai.openai_compatible_provider import OpenAICompatibleProvider
from app.infrastructure.ai.gemini_compatible_provider import GeminiCompatibleProvider
from app.infrastructure.ai.usage_logger import wrap_provider_with_logging


def create_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == "openai_compatible":
        provider = OpenAICompatibleProvider(
            base_url=settings.ai_base_url, api_key=settings.ai_api_key,
            model=settings.ai_model, timeout_seconds=settings.ai_timeout_seconds,
        )
    elif settings.ai_provider == "gemini_compatible":
        provider = GeminiCompatibleProvider(
            base_url=settings.ai_base_url, api_key=settings.ai_api_key,
            model=settings.ai_model, timeout_seconds=settings.ai_timeout_seconds,
        )
    else:
        provider = StubAIProvider()
    # No-op unless AI_USAGE_LOG_ENABLED=true (see Settings.ai_usage_log_enabled).
    return wrap_provider_with_logging(provider, settings)
