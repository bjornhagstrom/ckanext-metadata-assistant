"""The assistant's own settings pages for sysadmins: what the metadata check does, the instructions, and the old AI page.

The AI connection (model, key, time limits) is ckanext-ai-connector's and tested there.
"""

import pytest

from ckan.plugins import toolkit
from ckan.tests import factories, helpers

from ckanext.metadata_assistant import admin_settings

P = admin_settings.PREFIX
N = "ckanext.ai_connector."
SECRET = "test-key-value-that-must-never-show"

pytestmark = [
    pytest.mark.ckan_config("ckan.plugins", "metadata_assistant ai_connector"),
    pytest.mark.ckan_config(N + "model", "gemini/gemini-3.5-flash-lite"),
    pytest.mark.ckan_config(N + "api_key_env", "GEMINI_API_KEY"),
    pytest.mark.usefixtures("with_plugins", "clean_db"),
]


@pytest.fixture
def people():
    return {"sysadmin": factories.Sysadmin(), "editor": factories.User()}


def call(name, user, **data):
    return helpers.call_action(name, context={"user": user["name"], "ignore_auth": False}, **data)


def _headers(user):
    return {"Authorization": factories.APIToken(user=user["name"])["token"]}


def test_the_check_page_saves_only_its_own_fields_and_is_for_sysadmins(people, app):
    headers = _headers(people["sysadmin"])
    check = app.get("/ckan-admin/metadata-assistant/check", headers=headers).body
    assert "Markdown in descriptions" in check and "Check the addresses while the editor types" in check
    assert 'href="/ckan-admin/ai"' in check   # the AI tab goes straight to ckanext-ai-connector's page
    assert app.get("/ckan-admin/metadata-assistant/check", headers=_headers(people["editor"]), status=403)
    app.post("/ckan-admin/metadata-assistant/check", headers=headers,
             data={"markdown": "off", "check_addresses": "on", "step": "save"})
    assert toolkit.config.get(P + "markdown") == "off" and toolkit.config.get(P + "check_addresses") == "on"
    assert toolkit.config.get(N + "model") == "gemini/gemini-3.5-flash-lite"
    app.post("/ckan-admin/metadata-assistant/check", headers=headers, data={"step": "reset"})
    assert admin_settings.stored("markdown") is None


def test_the_panel_calls_the_api_in_the_language_of_the_page(people, app):
    """The rule check and the AI answer in the page's language only when the panel asks the API under that language."""
    headers = _headers(people["sysadmin"])
    assert 'data-api-base="/api/3/action/"' in app.get("/dataset/new", headers=headers).body
    assert 'data-api-base="/sv/api/3/action/"' in app.get("/sv/dataset/new", headers=headers).body


def test_the_rule_check_has_a_heading_of_its_own_apart_from_the_ai_suggestions(people, app):
    page = app.get("/dataset/new", headers=_headers(people["sysadmin"])).body
    assert "Rule check" in page and "checked without AI" in page
    assert page.index("Rule check") < page.index("metadata-assistant-review__rules")


def test_only_sysadmins_may_reset(people):
    with pytest.raises(toolkit.NotAuthorized):
        call("metadata_assistant_ai_settings_reset", people["editor"])
    admin_settings.save({"user": people["sysadmin"]["name"]}, {"markdown": "off"})
    assert call("metadata_assistant_ai_settings_reset", people["sysadmin"])["reset"] == list(admin_settings.CHECK_FIELDS)
    assert admin_settings.stored("markdown") is None


def test_the_instructions_page_says_when_the_ai_is_not_set_up(people, app, monkeypatch):
    headers = _headers(people["sysadmin"])
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert "The AI is not set up yet" in app.get("/ckan-admin/metadata-assistant/instructions", headers=headers).body
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    page = app.get("/ckan-admin/metadata-assistant/instructions", headers=headers).body
    assert "The AI is not set up yet" not in page and SECRET not in page


def test_reading_the_landing_page_when_the_form_opens_is_a_sysadmin_setting_that_is_on_by_default(people, app):
    from ckanext.metadata_assistant.link_results import read_page_on_open_enabled

    assert read_page_on_open_enabled() is True
    headers = _headers(people["sysadmin"])
    page = app.get("/ckan-admin/metadata-assistant/check", headers=headers).body
    assert 'name="read_page_on_open"' in page and "Read the landing page when the form opens" in page
    app.post("/ckan-admin/metadata-assistant/check", headers=headers,
             data={"markdown": "auto", "check_addresses": "off", "landing_page_fetch": "auto", "read_page_on_open": "off", "step": "save"})
    assert toolkit.config.get(P + "read_page_on_open") == "off" and read_page_on_open_enabled() is False
    with pytest.raises(toolkit.ValidationError):
        admin_settings.save({"user": people["sysadmin"]["name"]}, {"read_page_on_open": "sometimes"})
    app.post("/ckan-admin/metadata-assistant/check", headers=headers, data={"step": "reset"})
    assert read_page_on_open_enabled() is True


def test_the_admin_pages_work_with_a_trailing_slash_and_the_reset_button_is_always_there(people, app):
    headers = _headers(people["sysadmin"])
    for path in ("/ckan-admin/metadata-assistant/check/", "/ckan-admin/metadata-assistant/instructions/"):
        assert app.get(path, headers=headers, status=200)
    assert app.get("/ckan-admin/metadata-assistant/", headers=headers, follow_redirects=False).status_code == 302
    page = app.get("/ckan-admin/metadata-assistant/check", headers=headers).body
    assert 'value="reset" disabled' in page and "Nothing is saved here" in page


def test_the_old_ai_page_leads_to_the_shared_one_and_without_it_to_the_check_page(people, app, monkeypatch):
    """The connection is ckanext-ai-connector's: an old link goes to its page, or, without that plugin, to this extension's
    check page, which says why the AI is off."""
    headers = _headers(people["sysadmin"])
    response = app.get("/ckan-admin/metadata-assistant", headers=headers, follow_redirects=False)
    assert response.status_code == 302 and response.headers["Location"].endswith("/ckan-admin/ai")

    monkeypatch.setattr("ckan.plugins.plugin_loaded", lambda name: name != "ai_connector")
    response = app.get("/ckan-admin/metadata-assistant", headers=headers, follow_redirects=False)
    assert response.headers["Location"].endswith("/ckan-admin/metadata-assistant/check")
    page = app.get("/ckan-admin/metadata-assistant/check", headers=headers).body
    assert "the ai_connector plugin" in page and "Only the rule-based review works." in page
    assert "The AI is not set up yet" in app.get("/ckan-admin/metadata-assistant/instructions", headers=headers).body
