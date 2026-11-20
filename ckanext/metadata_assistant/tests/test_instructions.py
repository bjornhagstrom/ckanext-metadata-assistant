"""The instruction to the AI: the whole text is the catalogue's to edit, ours is only the default.

A review and a translation each have one instruction. Until something is saved the default in llm/prompts.py
applies; a saved text, even an empty one, is used exactly as it is.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ckan import model
from ckan.plugins import toolkit
from ckan.tests import factories, helpers

from ckanext.metadata_assistant import actions, admin_settings
from ckanext.metadata_assistant.llm import (
    MetadataReviewRequest,
    MetadataReviewResponse,
    TranslationRequest,
    prompts,
)

P = admin_settings.PREFIX
OWN = "Write for researchers. Name the measuring method in the description."

pytestmark = [
    pytest.mark.ckan_config("ckan.plugins", "metadata_assistant ai_connector"),
    pytest.mark.usefixtures("with_plugins", "clean_db"),
]


@pytest.fixture(autouse=True)
def fresh_cache(with_plugins, clean_db):
    # CKAN keeps the configured values aside once; earlier tests filled it.
    from ckan.lib import app_globals

    for name in admin_settings.INSTRUCTIONS:
        app_globals._CONFIG_CACHE.pop(P + name, None)
    app_globals.reset()


def test_a_catalogues_text_replaces_the_default_completely():
    request = MetadataReviewRequest(title="x", catalogue_instructions=OWN)
    assert prompts.review_system_prompt(request) == OWN
    assert "never invent facts" not in prompts.review_system_prompt(request)


def test_without_a_text_the_default_is_used_and_an_empty_text_means_no_instruction():
    assert prompts.review_system_prompt(MetadataReviewRequest(title="x")) == prompts.DEFAULT_REVIEW_INSTRUCTIONS
    assert prompts.review_system_prompt(MetadataReviewRequest(title="x", catalogue_instructions="")) == ""


def test_the_default_refers_to_the_facts_the_request_carries():
    text = prompts.DEFAULT_REVIEW_INSTRUCTIONS
    for fact in ("field_guidance", "owner_organisation", "catalogue_name", "markdown"):
        assert fact in text
    request = MetadataReviewRequest(title="x", owner_organisation="Org", catalogue_name="Cat", markdown=True)
    payload = prompts.user_prompt(request)
    for fact in ('"owner_organisation": "Org"', '"catalogue_name": "Cat"', '"markdown": true', '"field_guidance"'):
        assert fact in payload


def test_the_instructions_are_not_sent_as_part_of_the_material():
    request = MetadataReviewRequest(title="x", catalogue_instructions=OWN)
    assert OWN not in prompts.user_prompt(request)


def test_a_translation_text_gets_the_language_names_put_in():
    request = TranslationRequest(source_language="sv", target_language="en", title="x")
    prompt = prompts.translation_system_prompt(request)
    assert "Swedish" in prompt and "English" in prompt and "{source}" not in prompt and "{target}" not in prompt
    own = TranslationRequest(source_language="sv", target_language="en", title="x",
                             catalogue_instructions="Translate {source} to {target} formally.")
    assert prompts.translation_system_prompt(own) == "Translate Swedish to English formally."


def test_the_defaults_are_what_the_page_starts_from():
    assert admin_settings.instructions("ai_review_instructions") == prompts.DEFAULT_REVIEW_INSTRUCTIONS.strip()
    assert admin_settings.instructions("ai_translation_instructions") == prompts.DEFAULT_TRANSLATION_INSTRUCTIONS.strip()


def test_saved_instructions_apply_and_the_default_comes_back():
    sysadmin = factories.Sysadmin()
    context = {"user": sysadmin["name"]}
    admin_settings.save_instructions(context, {"ai_review_instructions": OWN,
                                               "ai_translation_instructions": ""})
    assert admin_settings.instructions("ai_review_instructions") == OWN
    # An emptied text means no instruction at all, not the default.
    assert admin_settings.instructions("ai_translation_instructions") == ""
    request = TranslationRequest(source_language="sv", target_language="en", title="x",
                                 catalogue_instructions="")
    assert prompts.translation_system_prompt(request) == ""

    # Saving the default text again is no override.
    admin_settings.save_instructions(context, {
        "ai_review_instructions": prompts.DEFAULT_REVIEW_INSTRUCTIONS})
    assert model.get_system_info(P + "ai_review_instructions") is None


def test_too_long_instructions_are_refused():
    sysadmin = factories.Sysadmin()
    with pytest.raises(toolkit.ValidationError):
        admin_settings.save_instructions({"user": sysadmin["name"]}, {
            "ai_review_instructions": "x" * (admin_settings.INSTRUCTIONS_MAX_LENGTH + 1)})


def test_only_a_sysadmin_may_try_a_draft():
    editor = factories.User()
    with pytest.raises(toolkit.NotAuthorized):
        actions._catalogue_instructions({"user": editor["name"]},
                                        {"catalogue_instructions": OWN},
                                        "ai_review_instructions")
    sysadmin = factories.Sysadmin()
    assert actions._catalogue_instructions({"user": sysadmin["name"]},
                                           {"catalogue_instructions": OWN},
                                           "ai_review_instructions") == OWN


def test_the_page_shows_the_whole_text_and_tries_a_draft_without_saving(app):
    sysadmin = factories.Sysadmin()
    dataset = factories.Dataset()
    headers = {"Authorization": factories.APIToken(user=sysadmin["name"])["token"]}
    page = " ".join(app.get("/ckan-admin/metadata-assistant/instructions", headers=headers).body.split())
    assert "never invent facts" in page  # the whole default text is in the field, nothing is locked
    assert "Built in" not in page

    seen = {}

    class Provider:
        def review(self, request):
            seen["instructions"] = request.catalogue_instructions
            return MetadataReviewResponse(summary="A trial answer.")

    profile = SimpleNamespace(title_field="title", description_field="notes",
                              keywords_field="tag_string", theme_field=None,
                              theme_allowed_values=frozenset(), field_guidance={})
    with patch.object(actions, "get_active_profile", return_value=profile), \
            patch.object(actions, "_metadata_language", return_value="sv"), \
            patch("ckanext.metadata_assistant.ai.assistant", return_value=Provider()):
        page = app.post("/ckan-admin/metadata-assistant/instructions", headers=headers, data={
            "step": "try", "dataset": "/dataset/" + dataset["name"],
            "ai_review_instructions": OWN, "ai_translation_instructions": ""}).body
    assert seen["instructions"] == OWN
    assert "A trial answer." in page
    assert model.get_system_info(P + "ai_review_instructions") is None


def test_outsiders_cannot_open_the_page(app):
    editor = factories.User()
    headers = {"Authorization": factories.APIToken(user=editor["name"])["token"]}
    assert app.get("/ckan-admin/metadata-assistant/instructions", headers=headers).status_code == 403


def test_a_translation_can_be_tried_with_a_draft(app):
    sysadmin = factories.Sysadmin()
    dataset = factories.Dataset()
    headers = {"Authorization": factories.APIToken(user=sysadmin["name"])["token"]}
    seen = {}

    def translate(context, data_dict):
        seen.update(data_dict)
        return {"suggestions": [{"label": "Title", "language_label": "English",
                                 "suggested_value": "Bathing sites",
                                 "source_language_label": "Swedish",
                                 "source_value": "Badplatser"}], "failed": []}

    with patch.dict("ckan.logic._actions", {"metadata_assistant_translate_dataset": translate}):
        page = app.post("/ckan-admin/metadata-assistant/instructions", headers=headers, data={
            "step": "try_translation", "dataset": dataset["name"],
            "ai_review_instructions": "", "ai_translation_instructions": OWN}).body
    assert seen == {"id": dataset["name"], "catalogue_instructions": OWN}
    assert "Bathing sites" in page and "Badplatser" in page
    assert model.get_system_info(P + "ai_translation_instructions") is None


def test_the_dataset_field_completes_names(app):
    sysadmin = factories.Sysadmin()
    headers = {"Authorization": factories.APIToken(user=sysadmin["name"])["token"]}
    page = app.get("/ckan-admin/metadata-assistant/instructions", headers=headers).body
    assert 'data-module-source="/api/2/util/dataset/autocomplete?incomplete=?"' in page


def test_the_default_says_the_landing_page_adds_to_the_description_and_never_replaces_it():
    text = " ".join(prompts.DEFAULT_REVIEW_INSTRUCTIONS.split())   # the text is wrapped in lines
    assert "never remove a fact" in text
    assert "it never replaces it" in text
    from ckanext.metadata_assistant.guidance import BASELINE_GUIDANCE

    assert "add to it rather than replace it" in BASELINE_GUIDANCE["notes"]


def test_the_defaults_keep_the_description_on_the_data_check_the_suggestions_and_write_real_letters():
    """After the browser test of 2026-11-19: a description about "this landing page" (an organisation's home page was
    given), a keyword its own reason ruled out, and "ue" for "ü" in a German translation."""
    review = " ".join(prompts.DEFAULT_REVIEW_INSTRUCTIONS.split())
    assert "never about the landing page" in review and "If the landing page is not about this dataset" in review
    assert "against its own reason" in review
    assert "who uses the data, for what or why only when the material says so" in review
    translation = " ".join(prompts.DEFAULT_TRANSLATION_INSTRUCTIONS.split())
    assert "own letters" in translation and '"ue" for "ü"' in translation
