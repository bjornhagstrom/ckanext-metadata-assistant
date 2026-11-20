"""Focused tests for the read-only semantic CKAN action."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ckanext.metadata_assistant import actions
from ckanext.metadata_assistant.llm import MetadataReviewResponse, ProviderError

import pytest

# Some of these reach CKAN's database (settings, users): in a fresh test database, as in CI, its tables exist only once a
# test has asked for them.
pytestmark = pytest.mark.usefixtures("clean_db")


PROFILE = SimpleNamespace(
    title_field="title",
    description_field="notes",
    keywords_field="tag_string",
    theme_field="theme",
    theme_allowed_values=frozenset({"theme:SOCI", "theme:ENVI"}),
)


class AIActionTests(unittest.TestCase):
    @patch("ckanext.metadata_assistant.ai.assistant")
    @patch.object(actions, "get_active_profile", return_value=PROFILE)
    @patch.object(actions, "_authorized_dataset")
    def test_builds_minimal_request_and_returns_validated_response(
        self, authorized_dataset, _active_profile, from_config
    ):
        authorized_dataset.return_value = {
            "title": "Badplatser",
            "notes": "Kort beskrivning.",
            "tag_string": "badplats, friluftsliv",
            "theme": ["theme:ENVI"],
            "language": "sv",
            "url": "https://example.org/badplatser",
            "private": True,
            "resources": [{"url": "https://example.invalid/private.csv"}],
        }
        provider = Mock()
        provider.review.return_value = MetadataReviewResponse(
            summary="Beskrivningen behöver utvecklas."
        )
        from_config.return_value = provider

        result = actions.metadata_assistant_ai_review_dataset({}, {"dataset": {}})

        request = provider.review.call_args.args[0]
        self.assertEqual(request.title, "Badplatser")
        self.assertEqual(request.keywords, ["badplats", "friluftsliv"])
        self.assertEqual(request.current_theme_uris, ["theme:ENVI"])
        self.assertEqual(request.landing_page_url, "https://example.org/badplatser")
        self.assertFalse(hasattr(request, "resources"))
        self.assertEqual(result["summary"], "Beskrivningen behöver utvecklas.")

    @patch("ckanext.metadata_assistant.ai.assistant")
    @patch.object(actions, "get_active_profile", return_value=PROFILE)
    @patch.object(actions, "_authorized_dataset", return_value={})
    def test_provider_error_becomes_safe_validation_error(
        self, _authorized_dataset, _active_profile, from_config
    ):
        provider = Mock()
        provider.review.side_effect = ProviderError("Säkert felmeddelande.")
        from_config.return_value = provider

        with self.assertRaises(actions.toolkit.ValidationError) as raised:
            actions.metadata_assistant_ai_review_dataset({}, {"dataset": {}})

        self.assertIn("Säkert felmeddelande", str(raised.exception))


if __name__ == "__main__":
    unittest.main()


class AiReviewAccessTests(unittest.TestCase):
    """Only editors and sysadmins may start the AI review (2026-09-27)."""

    @patch.object(actions.toolkit, "get_action")
    @patch.object(actions.toolkit, "check_access")
    def test_a_saved_dataset_needs_edit_rights(self, check_access, get_action):
        get_action.return_value = lambda context, data: {"id": "x"}
        actions._authorized_dataset({}, {"id": "x"}, require_edit=True)
        check_access.assert_called_once_with("package_update", {}, {"id": "x"})

    @patch.object(actions.toolkit, "get_action")
    @patch.object(actions.toolkit, "check_access")
    def test_the_rule_review_still_needs_only_read_rights(self, check_access, get_action):
        get_action.return_value = lambda context, data: {"id": "x"}
        actions._authorized_dataset({}, {"id": "x"})
        check_access.assert_called_once_with("package_show", {}, {"id": "x"})

    @patch.object(actions, "_authorized_dataset", side_effect=actions.toolkit.NotAuthorized)
    def test_the_ai_review_asks_for_edit_rights(self, authorized):
        with self.assertRaises(actions.toolkit.NotAuthorized):
            actions.metadata_assistant_ai_review_dataset({}, {"id": "x"})
        self.assertEqual(authorized.call_args.kwargs, {"require_edit": True})


class FluentFormTests(unittest.TestCase):
    """A ckanext-fluent form draft is reviewed in the main language."""

    @patch.object(actions.toolkit, "config", {"ckan.locale_default": "sv"})
    def test_main_language_becomes_the_plain_field(self):
        draft = {"title_translated-sv": "Badplatser", "title_translated-en": "Bathing sites",
                 "notes_translated-sv": "Text.", "tag_string": "badplats"}
        out = actions.normalize_fluent_form(draft)
        self.assertEqual(out["title"], "Badplatser")
        self.assertEqual(out["notes"], "Text.")
        self.assertEqual(out["tag_string"], "badplats")

    @patch.object(actions.toolkit, "config", {"ckan.locale_default": "sv"})
    def test_plain_fields_win_and_non_fluent_drafts_are_untouched(self):
        self.assertEqual(actions.normalize_fluent_form({"title": "A"}), {"title": "A"})
        out = actions.normalize_fluent_form({"title": "A", "title_translated-sv": "B"})
        self.assertEqual(out["title"], "A")


def test_keywords_the_dataset_already_has_are_not_suggested_again():
    from types import SimpleNamespace

    from ckanext.metadata_assistant.actions import _without_existing_keywords

    profile = SimpleNamespace(keywords_field="tag_string")
    result = {"summary": "s", "suggestions": [
        {"field": "title", "suggested_value": "Ny titel", "reason": "r"},
        {"field": "tag_string", "suggested_value": ["Nyckelkodsområde", "kartlager", "kartlager"], "reason": "r"},
        {"field": "tag_string", "suggested_value": "geodata", "reason": "only repeats"}]}
    out = _without_existing_keywords(result, profile, ["geodata", "nyckelkodsområde"])
    assert [s["field"] for s in out["suggestions"]] == ["title", "tag_string"]
    assert out["suggestions"][1]["suggested_value"] == ["kartlager"]
    assert out["summary"] == "s"


def test_the_ai_is_told_whose_catalogue_it_is():
    from ckanext.metadata_assistant.actions import _owner_organisation
    from ckanext.metadata_assistant.llm import MetadataReviewRequest
    from ckanext.metadata_assistant.llm.prompts import user_prompt

    assert _owner_organisation({"organization": {"title": "Externa datakällor"}}) == "Externa datakällor"
    assert _owner_organisation({}) == ""
    request = MetadataReviewRequest(title="Polisens händelser Malmö", owner_organisation="Externa datakällor",
                                    catalogue_name="Metadatakatalog")
    prompt = user_prompt(request)
    assert '"owner_organisation": "Externa datakällor"' in prompt
    assert '"catalogue_name": "Metadatakatalog"' in prompt


def test_the_baseline_keeps_another_publishers_name_and_the_place_the_data_is_about():
    from ckanext.metadata_assistant.guidance import BASELINE_GUIDANCE

    title = BASELINE_GUIDANCE["title"]
    assert "owner_organisation" in title
    assert "Another organisation's name stays" in title
    assert "A place name stays when the data is about that place" in title
    assert "Never add a name or a place to a title that has none" in title
    keywords = " ".join(BASELINE_GUIDANCE["tag_string"].split())
    assert "a housing area" in keywords and "is a good keyword" in keywords   # what the data is about may be a keyword
    assert "whole area the catalogue itself covers" in keywords


def test_the_baseline_guidance_names_the_catalogues_own_organisation_and_leaves_others_alone():
    from types import SimpleNamespace

    from ckanext.metadata_assistant.actions import _guidance_for_request
    from ckanext.metadata_assistant.guidance import BASELINE_GUIDANCE

    profile = SimpleNamespace(title_field="title", description_field="notes", keywords_field="tag_string",
                              theme_field=None, field_guidance={
                                  "title": BASELINE_GUIDANCE["title"], "notes": "N.",
                                  "tag_string": BASELINE_GUIDANCE["tag_string"]})
    guidance = _guidance_for_request(profile, "Externa datakällor", "Metadatakatalog")
    assert '"Externa datakällor"' in guidance["title"] and '"Metadatakatalog"' in guidance["title"]
    assert "any other organisation" in guidance["title"]
    assert guidance["notes"] == "N."
    assert _guidance_for_request(profile, "", "")["title"] == BASELINE_GUIDANCE["title"]


def test_a_schemas_own_help_text_is_passed_on_unchanged():
    from types import SimpleNamespace

    from ckanext.metadata_assistant.actions import _guidance_for_request

    profile = SimpleNamespace(title_field="title", description_field="notes", keywords_field="tag_string",
                              theme_field=None, field_guidance={"title": "Our own rule: no place names."})
    assert _guidance_for_request(profile, "Kommunen", "Katalogen")["title"] == "Our own rule: no place names."


class UnchangedSuggestionTests(unittest.TestCase):
    def test_a_title_or_description_equal_to_the_current_text_is_dropped(self):
        request = SimpleNamespace(title="Vägar", description="Malmö stads vägar.\nMed mera.")
        result = {"suggestions": [
            {"field": "title", "suggested_value": "Vägar"},
            {"field": "notes", "suggested_value": "Malmö stads  vägar. Med mera. "},
            {"field": "tag_string", "suggested_value": "väg"}]}
        kept = actions._without_unchanged_text(result, PROFILE, request)["suggestions"]
        self.assertEqual([s["field"] for s in kept], ["tag_string"])
        changed = {"suggestions": [{"field": "notes", "suggested_value": "Malmö stads vägar och gator."}]}
        self.assertEqual(len(actions._without_unchanged_text(changed, PROFILE, request)["suggestions"]), 1)


def test_the_review_adds_what_the_link_check_found_when_it_is_installed(monkeypatch):
    pytest.importorskip("ckanext.link_check")   # optional: its results are read through its own module
    from ckan import plugins
    from ckan.plugins import toolkit

    from ckanext.metadata_assistant import link_results
    from ckanext.metadata_assistant.rules.profile import RuleProfile

    profile = RuleProfile.from_scheming_dict("p", {"dataset_fields": [], "resource_fields": []})
    dataset = {"id": "d1", "url": "https://www.etsi.org/standards", "resources": [{"id": "r1", "url": "https://gone.example/f.csv"}]}
    results = [
        {"url": "https://www.etsi.org/standards", "field": "url", "resource_id": None, "state": "redirect",
         "final_url": "https://www.etsi.org/standards/", "message": ""},
        {"url": "https://gone.example/f.csv", "field": "url", "resource_id": "r1", "state": "broken", "final_url": None, "message": ""},
        {"url": "https://changed-since.example/", "field": "url", "resource_id": None, "state": "broken", "final_url": None, "message": ""},
    ]
    monkeypatch.setattr(plugins, "plugin_loaded", lambda name: name == "link_check")
    monkeypatch.setattr(link_results.toolkit, "get_action", lambda name: (lambda context, data: {"results": results}))
    codes = [f.code for f in link_results.findings_from_link_check(dataset, profile, {"user": "x"})]
    assert codes == ["link_forwards", "link_broken"]  # the one that is not in the dataset any more is left out
    monkeypatch.setattr(plugins, "plugin_loaded", lambda name: False)
    assert link_results.findings_from_link_check(dataset, profile, {"user": "x"}) == []
    assert link_results.findings_from_link_check({"url": "https://x"}, profile, {"user": "x"}) == []  # an unsaved draft


def test_addresses_the_editor_has_just_typed_are_checked_when_the_sysadmin_has_turned_it_on(monkeypatch):
    from ckan import plugins
    from ckan.plugins import toolkit

    from ckanext.metadata_assistant import link_results
    from ckanext.metadata_assistant.rules.profile import RuleProfile

    profile = RuleProfile.from_scheming_dict("p", {"dataset_fields": [], "resource_fields": []})
    answers = {
        "https://a.example/old": {"state": "redirect", "final_url": "https://a.example/old/", "suggestion": {"address": "https://a.example/old/", "kind": "slash"}},
        "https://b.example/page": {"state": "redirect", "final_url": "https://b.example/elsewhere", "suggestion": None},
        "https://c.example/gone": {"state": "broken", "final_url": None, "suggestion": None},
        "https://d.example/fine": {"state": "ok", "final_url": None, "suggestion": None},
    }

    def get_action(name):
        def call(context, data):
            if data["url"] == "https://e.example/limit":
                raise toolkit.ValidationError({"url": ["Too many"]})
            if data["url"] == "https://f.example/slip":
                raise RuntimeError("network slip")
            return answers[data["url"]]
        return call

    monkeypatch.setattr(plugins, "plugin_loaded", lambda name: name == "link_check")
    monkeypatch.setitem(toolkit.config, link_results.OPTION, "on")
    monkeypatch.setattr(link_results.toolkit, "get_action", get_action)
    found = link_results.live_findings(list(answers) + ["https://e.example/limit", "https://f.example/slip"], profile, {"user": "x"})
    # at most five addresses are checked; the one that is fine, the rate-limited one and the one that slipped say nothing
    assert [(a, f.code) for a, f in found] == [("https://a.example/old", "link_forwards_now"),
                                              ("https://b.example/page", "link_forwards_unclear"),
                                              ("https://c.example/gone", "link_broken_now")]
    monkeypatch.setitem(toolkit.config, link_results.OPTION, "off")
    assert link_results.live_findings(list(answers), profile, {"user": "x"}) == []
    monkeypatch.setitem(toolkit.config, link_results.OPTION, "on")
    monkeypatch.setattr(plugins, "plugin_loaded", lambda name: False)
    assert link_results.live_findings(list(answers), profile, {"user": "x"}) == []


def test_a_plain_http_address_that_also_answers_over_https_gets_the_https_address_as_its_suggestion(monkeypatch):
    from ckan import plugins
    from ckan.plugins import toolkit

    from ckanext.metadata_assistant import link_results
    from ckanext.metadata_assistant.rules.profile import RuleProfile

    profile = RuleProfile.from_scheming_dict("p", {"dataset_fields": [], "resource_fields": []})
    answers = {
        "http://a.example/page": {"state": "ok", "final_url": None, "suggestion": {"address": "https://a.example/page", "kind": "https"}},
        "http://b.example/page": {"state": "ok", "final_url": None, "suggestion": None},
        "http://c.example/old": {"state": "redirect", "final_url": "https://c.example/old/", "suggestion": {"address": "https://c.example/old/", "kind": "https"}},
    }
    monkeypatch.setattr(plugins, "plugin_loaded", lambda name: name == "link_check")
    monkeypatch.setitem(toolkit.config, link_results.OPTION, "on")
    monkeypatch.setattr(link_results.toolkit, "get_action", lambda name: lambda context, data: answers[data["url"]])
    found = link_results.live_findings(list(answers), profile, {"user": "x"})
    # the address with no https to offer says nothing here (the rule about http:// covers it)
    assert [(a, f.code, f.suggestion) for a, f in found] == [
        ("http://a.example/page", "link_use_https_now", "https://a.example/page"),
        ("http://c.example/old", "link_forwards_now", "https://c.example/old/")]


def test_the_setting_accepts_on_and_off_only():
    import pytest

    from ckan.plugins import toolkit

    from ckanext.metadata_assistant import admin_settings

    assert admin_settings._on_off("") == "off" and admin_settings._on_off(" On ") == "on"
    with pytest.raises(toolkit.Invalid):
        admin_settings._on_off("maybe")


@pytest.mark.ckan_config("ckan.plugins", "metadata_assistant ai_connector")
@pytest.mark.usefixtures("with_plugins")
def test_the_review_action_returns_the_live_findings_with_their_address(monkeypatch):
    from ckan.plugins import toolkit

    from ckanext.metadata_assistant import actions, link_results
    from ckanext.metadata_assistant.rules.engine import Finding

    sysadmin = {"user": "x", "ignore_auth": True}
    finding = Finding(field="", severity="warning", code="link_broken_now", message="m", source="s")
    monkeypatch.setattr(actions, "live_findings", lambda addresses, profile, context: [("https://x.example/", finding)])
    result = toolkit.get_action("metadata_assistant_review_dataset")(
        dict(sysadmin), {"dataset": {"title": "t"}, "check_addresses": ["https://x.example/"]})
    assert [f for f in result["findings"] if f.get("address")] == [
        {"field": "", "label": "", "severity": "warning", "code": "link_broken_now", "message": "m", "source": "s",
         "address": "https://x.example/", "suggestion": ""}]
