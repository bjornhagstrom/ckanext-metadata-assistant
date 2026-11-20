"""Contracts and the AI work of the semantic review (over ckanext-ai-connector's shared connection)."""

from ckanext.metadata_assistant.llm.base import (
    LLMProvider,
    ProviderConfigurationError,
    ProviderError,
    ProviderResponseError,
)
from ckanext.metadata_assistant.llm.contracts import (
    FieldSuggestion,
    LandingPageExtract,
    MetadataReviewRequest,
    MetadataReviewResponse,
    ThemeChoice,
    TranslationRequest,
    TranslationResponse,
)

__all__ = [
    "FieldSuggestion",
    "LLMProvider",
    "LandingPageExtract",
    "MetadataReviewRequest",
    "MetadataReviewResponse",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderResponseError",
    "ThemeChoice",
    "TranslationRequest",
    "TranslationResponse",
]
