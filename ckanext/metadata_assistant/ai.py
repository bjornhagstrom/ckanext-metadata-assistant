"""Whether the shared AI connection (ckanext-ai-connector) can be used here, and the assistant's AI over it.

The AI features need ckanext-ai-connector, its ``ai_connector`` plugin and version ``MIN_API`` of its API, a model and a key.
When something is missing the AI features are off and the settings pages say why; the rule-based check works as before and
CKAN starts. Only ``ckanext.ai_connector.api`` is used here.
"""

MIN_API = 2
# What the assistant uses the AI for (API 2): the AI settings page can give each its own model; without one, the main model.
REVIEW, TRANSLATE, LANDING_PAGE = "review", "translate", "landing_page"
KIND_PURPOSES = {"review": REVIEW, "translate": TRANSLATE, "landing": LANDING_PAGE}

try:
    from ckanext.ai_connector import api
except ImportError:   # installed without its dependency (pip --no-deps)
    api = None


def declare_purposes():
    """Name the assistant's purposes for the AI settings page (called when the plugin loads)."""
    from ckanext.metadata_assistant.llm.assistant import CONSUMER
    from ckanext.metadata_assistant.localization import _

    if api is None or getattr(api, "API_VERSION", 1) < 2:
        return
    labels = {REVIEW: lambda: _("Metadata review"), TRANSLATE: lambda: _("Translation of metadata"),
              LANDING_PAGE: lambda: _("Reading landing pages")}
    if getattr(api, "API_VERSION", 1) >= 3:   # the page names the extension over its purposes
        api.declare_purposes(CONSUMER, labels, name=lambda: _("Metadata assistant"))
    else:
        api.declare_purposes(CONSUMER, labels)


def problem(purpose=None):
    """Why the AI cannot be used here (for that purpose), as a sentence for a sysadmin, or None when it can."""
    from ckanext.metadata_assistant.llm.assistant import CONSUMER
    from ckanext.metadata_assistant.localization import _

    if api is None:
        return _("The AI features need ckanext-ai-connector, which is not installed.")
    if purpose is None or getattr(api, "API_VERSION", 1) < 2:
        return api.unavailable_reason(min_api=MIN_API)   # (an API older than 2 says so, without the new arguments)
    # A purpose with a model of its own can work while the main connection cannot: the connection says.
    return api.unavailable_reason(min_api=MIN_API, consumer=CONSUMER, purpose=purpose)


def ready(purpose=None):
    """Can the AI be used here (for that purpose)?"""
    return problem(purpose) is None


def model(purpose=None):
    """The model in use for a purpose, or "" (for the caches: a review or a page read by another model is another one)."""
    from ckanext.metadata_assistant.llm.assistant import CONSUMER

    if api is None:
        return ""
    try:
        return api.describe(CONSUMER, purpose)["model"] if purpose else api.describe()["model"]
    except Exception:
        return ""


def assistant(purpose=None, **options):
    """The assistant's AI over a new client for a purpose. Raises ProviderConfigurationError with the reason when it cannot
    be used."""
    from ckanext.metadata_assistant.llm.assistant import CONSUMER, MetadataAI
    from ckanext.metadata_assistant.llm.base import ProviderConfigurationError

    reason = problem(purpose)
    if reason:
        raise ProviderConfigurationError(reason)
    try:
        client = api.client(CONSUMER, purpose=purpose, max_attempts=1)
    except api.AIConfigurationError as error:
        raise ProviderConfigurationError(str(error)) from None
    return MetadataAI(client, **options)
