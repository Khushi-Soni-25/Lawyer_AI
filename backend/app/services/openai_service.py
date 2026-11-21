"""Compatibility import for integrations that still import the former module.

The active provider is Gemini; new code must import :class:`GeminiService`.
"""

from backend.app.services.gemini_service import GeminiService


OpenAIResponsesService = GeminiService
