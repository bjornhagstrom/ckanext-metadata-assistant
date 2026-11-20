import os

import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit

from ckanext.metadata_assistant import actions, admin_settings, auth, cli, jobs, markdown, model, multilingual, views  # noqa: F401 (model registers the table)


from ckanext.metadata_assistant.link_results import live_check_enabled, read_page_on_open_enabled


@toolkit.blanket.config_declarations
class MetadataAssistantPlugin(plugins.SingletonPlugin):
    """Metadata quality review (rule-based checks and AI suggestions), wired into CKAN.

    Needs no configuration of the metadata schema: it uses the schema file named by
    ``ckanext.metadata_assistant.schema_file`` if set, else the schema ckanext-scheming
    has loaded, else CKAN's own fields (see ckanext.metadata_assistant.profiles).
    """

    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IValidators)
    plugins.implements(plugins.ITranslation)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.IClick)

    def get_commands(self):
        return cli.get_commands()

    def get_auth_functions(self):
        return {"metadata_assistant_ai_settings": auth.ai_settings}

    # IConfigurer: the AI settings a sysadmin may change at runtime
    # (2026-10-03). Keys stay in the server's configuration; see admin_settings.
    def update_config_schema(self, schema):
        return admin_settings.update_config_schema(schema)

    def get_helpers(self):
        helpers = {"metadata_assistant_translation_languages": translation_languages,
                   "metadata_assistant_markdown_enabled": markdown_enabled,
                   "metadata_assistant_check_addresses": live_check_enabled,
                   "metadata_assistant_read_page_on_open": read_page_on_open_enabled,
                   "metadata_assistant_number": number, "metadata_assistant_percent": percent,
                   "metadata_assistant_ai_settings_url": views.ai_settings_url}
        helpers.update(multilingual.missing_fields_helper())
        return helpers

    # ITranslation (2026-10-01). English is the source language of the
    # interface; the Swedish catalogues are compiled from i18n/sv and i18n/sv_SE. The AI's own
    # texts (prompts, suggestions) are not interface texts and are not here.
    def i18n_directory(self):
        return os.path.join(os.path.dirname(__file__), "i18n")

    def i18n_locales(self):
        directory = self.i18n_directory()
        return sorted(
            locale for locale in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, locale, "LC_MESSAGES", self.i18n_domain() + ".mo")))

    def i18n_domain(self):
        return "ckanext-metadata-assistant"

    def get_validators(self):
        from ckanext.metadata_assistant.rules.translations import (
            translation_state_validator,
        )

        # Marked as a ckanext-scheming validator factory (called with the
        # field and schema) without importing scheming, which stays optional.
        translation_state_validator.is_a_scheming_validator = True
        return {
            "metadata_assistant_translation_state": translation_state_validator,
            # Multilingual title, description and keywords (see multilingual.py).
            "metadata_assistant_fluent_from_core": _scheming(multilingual.fluent_from_core),
            "metadata_assistant_fluent_to_core": _scheming(multilingual.fluent_to_core),
            "metadata_assistant_fluent_tags_strip": multilingual.fluent_tags_strip,
            "metadata_assistant_fluent_tags_output": multilingual.fluent_tags_output,
        }

    def update_config(self, config):
        toolkit.add_template_directory(config, "templates")
        toolkit.add_resource("assets", "metadata_assistant")

    def get_blueprint(self):
        return views.blueprint

    def get_actions(self):
        return {
            "metadata_assistant_review_dataset": actions.metadata_assistant_review_dataset,
            "metadata_assistant_ai_review_dataset": (
                actions.metadata_assistant_ai_review_dataset
            ),
            "metadata_assistant_read_landing_page": (
                actions.metadata_assistant_read_landing_page
            ),
            "metadata_assistant_translate_dataset": (
                actions.metadata_assistant_translate_dataset
            ),
            "metadata_assistant_job_start": jobs.metadata_assistant_job_start,
            "metadata_assistant_job_status": jobs.metadata_assistant_job_status,
            "metadata_assistant_status": actions.metadata_assistant_status,
            "metadata_assistant_render_markdown": actions.metadata_assistant_render_markdown,
            "metadata_assistant_catalogue_overview": actions.metadata_assistant_catalogue_overview,
            "metadata_assistant_ai_settings_reset": (
                actions.metadata_assistant_ai_settings_reset
            ),
        }


def _locale():
    from babel import Locale

    try:
        return Locale.parse(toolkit.h.lang() or "en", sep="_")
    except Exception:
        return Locale("en")


def number(value):
    """A number written the way the page's language writes it."""
    from babel.numbers import format_decimal

    return format_decimal(value, locale=_locale())


def percent(part, whole):
    """A share as a percent, written the way the page's language writes it."""
    from babel.numbers import format_percent

    return format_percent((part / whole) if whole else 0, locale=_locale())


def markdown_enabled():
    """Whether descriptions are Markdown here (the panel's preview and the AI's instruction)."""
    from ckanext.metadata_assistant.profiles import get_active_profile

    try:
        return markdown.enabled(get_active_profile())
    except Exception:
        return False


def _scheming(factory):
    """Mark a validator factory as taking the field and schema, without importing scheming."""
    factory.is_a_scheming_validator = True
    return factory


def translation_languages():
    """The profile's target languages, with names in the page's language,
    for the panel's translation button. Empty without a profile."""
    from ckanext.metadata_assistant.localization import language_name
    from ckanext.metadata_assistant.profiles import get_active_profile

    try:
        profile = get_active_profile()
    except Exception:
        return []
    if not profile.translation_targets:
        return []
    return [{"code": code, "label": language_name(code)} for code in profile.target_languages]
