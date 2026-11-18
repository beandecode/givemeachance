"""LLM adapters. Use `get_llm(settings)` instead of constructing an adapter directly."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adapters.llm.gemini_api import GeminiApiEvaluator
    from adapters.llm.mock_gemini import MockGeminiEvaluator
    from core.schemas import Settings


def get_llm(
    settings: Settings, quota_subject: str | None = None, model: str | None = None
) -> GeminiApiEvaluator | MockGeminiEvaluator:
    """The configured LLM adapter (`model` overrides the configured one); the live one charges `quota_subject`."""
    if settings.llm.provider == "gemini_api":
        from adapters.llm.gemini_api import GeminiApiEvaluator

        return GeminiApiEvaluator(
            model_name=model or settings.llm.model,
            db_path=settings.app.db_path,
            daily_limit=settings.api_limits.gemini_daily_limit,
            global_daily_limit=settings.api_limits.gemini_global_daily_limit,
            quota_subject=quota_subject,
        )
    from adapters.llm.mock_gemini import MockGeminiEvaluator

    return MockGeminiEvaluator(model_name=model or settings.llm.model)
