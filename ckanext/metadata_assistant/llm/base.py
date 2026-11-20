"""The errors of an AI call, under the names this extension has always used.

They are ckanext-ai-connector's (``api.AIError`` and its subclasses), so an ``except ProviderError`` catches a failure of the
shared client too, with its ``status_code`` and ``retryable``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ckanext.metadata_assistant.llm.contracts import MetadataReviewRequest, MetadataReviewResponse

try:
    from ckanext.ai_connector.api import AIConfigurationError, AIError, AIResponseError
except ImportError:   # ckanext-ai-connector missing: the AI is off (see ai.py), the names still exist
    class AIError(RuntimeError):
        def __init__(self, message="", *, status_code=None, retryable=False):
            super().__init__(message)
            self.status_code = status_code
            self.retryable = retryable

    class AIConfigurationError(AIError):
        pass

    class AIResponseError(AIError):
        pass

ProviderError = AIError
ProviderConfigurationError = AIConfigurationError
ProviderResponseError = AIResponseError


@runtime_checkable
class LLMProvider(Protocol):
    """What the actions need for a review (``MetadataAI`` has it)."""

    def review(self, request: MetadataReviewRequest) -> MetadataReviewResponse:
        """Review selected metadata without saving or publishing anything."""
