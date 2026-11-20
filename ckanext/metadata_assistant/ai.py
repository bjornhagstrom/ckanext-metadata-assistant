"""Whether the shared AI connection (ckanext-ai-connector) can be used here, and the assistant's AI over it.

The AI features need ckanext-ai-connector, its ``ai_connector`` plugin and version ``MIN_API`` of its API, a model and a key.
When something is missing the AI features are off and the settings pages say why; the rule-based check works as before and
CKAN starts. Only ``ckanext.ai_connector.api`` is used here.
"""

MIN_API = 1

try:
    from ckanext.ai_connector import api
except ImportError:   # installed without its dependency (pip --no-deps)
    api = None


def problem():
    """Why the AI cannot be used here, as a sentence for a sysadmin, or None when it can."""
    from ckanext.metadata_assistant.localization import _

    if api is None:
        return _("The AI features need ckanext-ai-connector, which is not installed.")
    return api.unavailable_reason(min_api=MIN_API)


def ready():
    """Can the AI be used here?"""
    return problem() is None


def model():
    """The model in use, or "" (for the cache of prepared reviews: a review by another model is another review)."""
    if api is None:
        return ""
    try:
        return api.describe()["model"]
    except Exception:
        return ""


def assistant(**options):
    """The assistant's AI over a new client. Raises ProviderConfigurationError with the reason when it cannot be used."""
    from ckanext.metadata_assistant.llm.assistant import CONSUMER, MetadataAI
    from ckanext.metadata_assistant.llm.base import ProviderConfigurationError

    reason = problem()
    if reason:
        raise ProviderConfigurationError(reason)
    return MetadataAI(api.client(CONSUMER, max_attempts=1), **options)
