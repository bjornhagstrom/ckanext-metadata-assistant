"""The portal's own language, not a built-in one (2026-11-20): labels, help texts, resource names and the landing page's
Accept-Language follow ``ckan.locale_default`` and the page's language."""

import pytest

from ckanext.metadata_assistant import localization, page_fetch
from ckanext.metadata_assistant.localization import pick_language

TEXTS = {"sv": "Titel", "fi": "Otsikko", "en": "Title", "de": ""}


@pytest.mark.ckan_config("ckan.locale_default", "fi")
def test_the_portals_language_comes_before_english_and_a_swedish_one(monkeypatch):
    monkeypatch.setattr(localization, "ui_language", lambda: "en")
    assert pick_language(TEXTS, page=False) == "Otsikko"
    assert pick_language(TEXTS) == "Title"   # the page's language first
    monkeypatch.setattr(localization, "ui_language", lambda: "sv_SE")
    assert pick_language(TEXTS) == "Titel"   # sv_SE matches sv


@pytest.mark.ckan_config("ckan.locale_default", "de")
def test_an_empty_text_is_passed_over_and_anything_else_falls_back(monkeypatch):
    monkeypatch.setattr(localization, "ui_language", lambda: "de")
    assert pick_language(TEXTS) == "Title"
    assert pick_language({"sv": "Bara svenska"}) == "Bara svenska"
    assert pick_language({}, default="name") == "name" and pick_language("plain") == "plain"


@pytest.mark.parametrize("locale, header", [("fi", "fi,en;q=0.7"), ("pt_BR", "pt-BR,en;q=0.7"), ("en", "en"),
                                            ("en_GB", "en")])
def test_a_landing_page_is_asked_for_in_the_portals_language(locale, header, ckan_config, monkeypatch):
    monkeypatch.setitem(ckan_config, "ckan.locale_default", locale)
    assert page_fetch._accept_language() == header


# --- the call sites (ckan-reviewer 2026-11-20: each must fail if it went back to a built-in language) --------------------

STATE_FIELD = {"field_name": "translation_hashes",
               "translation_targets": {"title_translated": "title_translated"},
               "target_languages": {"en": "recommended"}}


@pytest.mark.ckan_config("ckan.locale_default", "pt_BR")
def test_without_a_source_language_the_profile_and_the_validator_both_use_the_portals_whole_code():
    import json

    from ckanext.metadata_assistant.profiles import build_profile
    from ckanext.metadata_assistant.rules.translations import source_digest, translation_state_validator

    profile = build_profile({"dataset_fields": [{"field_name": "title"}, STATE_FIELD]})
    assert profile.source_language == "pt_BR"
    data = {("title",): "Praias", ("title_translated",): json.dumps({"pt_BR": "Praias", "en": "Beaches"}),
            ("translation_hashes",): ""}
    translation_state_validator(STATE_FIELD, {})(("translation_hashes",), data, {}, {})
    assert json.loads(data[("translation_hashes",)]) == {"title_translated:en": source_digest("Praias")}


@pytest.mark.ckan_config("ckan.locale_default", "fi")
def test_theme_labels_and_help_texts_for_the_ai_are_in_the_portals_language_whatever_the_page(monkeypatch):
    from ckanext.metadata_assistant.profiles import build_profile

    monkeypatch.setattr(localization, "ui_language", lambda: "en")
    profile = build_profile({"dataset_fields": [
        {"field_name": "title", "label": {"en": "Title", "fi": "Otsikko"},
         "help_text": {"en": "A short title.", "fi": "Lyhyt otsikko."}},
        {"field_name": "theme", "choices": [{"value": "http://example.org/t/env",
                                              "label": {"en": "Environment", "fi": "Ympäristö"}}]}]})
    assert profile.field_guidance["title"] == "Lyhyt otsikko."
    assert profile.theme_labels["http://example.org/t/env"] == "Ympäristö"
    assert profile.label("title") == "Title"   # the editor's page is in English


@pytest.mark.ckan_config("ckan.locale_default", "fi")
def test_a_resource_without_a_plain_name_is_named_in_the_portals_language(monkeypatch):
    from ckanext.metadata_assistant.rules import links

    monkeypatch.setattr(localization, "ui_language", lambda: "fi")
    assert links._name({"name_translated": {"sv": "Data", "fi": "Tiedot", "en": "Data file"}}) == "Tiedot"



def test_a_landing_page_is_asked_for_in_a_given_language_first():
    assert page_fetch._accept_language("sv") == "sv,en;q=0.7"
