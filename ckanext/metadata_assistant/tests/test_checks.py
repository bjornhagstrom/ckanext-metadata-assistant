"""The setup check: the metadata check page, the status action and the doctor command."""

from unittest.mock import patch

import pytest
from ckan.plugins import toolkit
from ckan.tests import factories, helpers

from ckanext.metadata_assistant import admin_settings, checks

P = admin_settings.PREFIX
# The connection's settings are ckanext-ai-connector's (2026-11-18), under its own names only; this extension's old names
# are moved by `ckan metadata-assistant migrate-ai-settings`.
N = "ckanext.ai_connector."

pytestmark = [
    pytest.mark.ckan_config("ckan.plugins", "metadata_assistant ai_connector"),
    pytest.mark.usefixtures("with_plugins", "clean_db"),
]


@pytest.fixture
def metadata_assistant_db(with_plugins, clean_db, migrate_db_for):
    migrate_db_for("metadata_assistant")


def by_key(result):
    return {c["key"]: c for c in result}


@pytest.mark.usefixtures("metadata_assistant_db")
def test_the_assistants_table_is_found_once_the_database_is_upgraded():
    assert by_key(checks.run_checks())["database"]["status"] == checks.OK


def test_a_missing_table_is_an_error_that_names_the_command():
    with patch("sqlalchemy.inspect") as inspect:
        inspect.return_value.has_table.return_value = False
        database = by_key(checks.run_checks())["database"]
    assert database["status"] == checks.ERROR
    assert "db upgrade -p metadata_assistant" in database["fix"]


@pytest.mark.ckan_config(N + "model", "")
def test_without_an_ai_model_only_a_note_is_made_and_nothing_fails():
    found = by_key(checks.run_checks())
    assert found["ai_connector"]["status"] == checks.WARN and "No AI model" in found["ai_connector"]["detail"]


@pytest.mark.ckan_config(N + "model", "gemini/gemini-3.5-flash-lite")
@pytest.mark.ckan_config(N + "api_key_env", "GEMINI_API_KEY")
def test_a_missing_key_is_a_note_that_says_why(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    found = by_key(checks.run_checks())["ai_connector"]
    assert found["status"] == checks.WARN and "No API key" in found["detail"]


@pytest.mark.ckan_config(N + "model", "gemini/gemini-3.5-flash-lite")
@pytest.mark.ckan_config(N + "api_key_env", "GEMINI_API_KEY")
def test_a_key_that_is_found_is_never_shown(monkeypatch):
    secret = "a-secret-key-that-must-not-appear-anywhere"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    result = checks.run_checks()
    assert by_key(result)["ai_connector"]["status"] == checks.OK
    assert "gemini/gemini-3.5-flash-lite" in by_key(result)["ai_connector"]["detail"]
    assert secret not in repr(result)


@pytest.mark.ckan_config(P + "ai_model", "gemini/an-old-server-option")
def test_old_settings_that_wait_to_be_moved_are_named_with_the_command():
    from ckan import model

    model.set_system_info(P + "ai_api_key_env", "GEMINI_API_KEY")
    found = by_key(checks.run_checks())["ai_migration"]
    assert found["status"] == checks.WARN and "migrate-ai-settings" in found["fix"]
    assert P + "ai_api_key_env" in found["detail"] and "CKANEXT__METADATA_ASSISTANT__AI_MODEL" in found["detail"]
    assert "an-old-server-option" not in found["detail"]   # names, never values


def test_a_portal_without_a_schema_is_told_translations_are_off():
    found = by_key(checks.run_checks())
    assert found["profile"]["status"] == checks.OK
    assert "ckan_core" in found["profile"]["detail"]
    assert found["languages"]["status"] == checks.WARN


def test_the_status_action_is_for_sysadmins_only():
    sysadmin, editor = factories.Sysadmin(), factories.User()
    result = helpers.call_action("metadata_assistant_status",
                                 context={"user": sysadmin["name"], "ignore_auth": False})
    assert {"ok", "checks"} <= set(result)
    with pytest.raises(toolkit.NotAuthorized):
        helpers.call_action("metadata_assistant_status",
                            context={"user": editor["name"], "ignore_auth": False})


def _profile(**kw):
    from ckanext.metadata_assistant.rules.profile import RuleProfile

    return RuleProfile(name="test", **kw)


def test_the_landing_page_check_says_what_is_missing_and_what_to_do():
    """The landing page is what the AI has most to go on: missing, hidden or optional gives a note with what to do."""
    with_url = {"title": "Title", "url": "Landing page"}
    assert checks._landing_page(None) == []
    missing = checks._landing_page(_profile(field_labels={"title": "Title"}))[0]
    assert missing["status"] == checks.WARN and "no landing page field" in missing["detail"]
    with patch.object(checks, "_form_level", return_value={"level": "optional", "hidden": False}):
        optional = checks._landing_page(_profile(field_labels=with_url, recommended_fields=("url",)))[0]
    assert optional["status"] == checks.WARN and "url: recommended" in optional["fix"]
    with patch.object(checks, "_form_level", return_value={"level": "recommended", "hidden": True}):
        assert "hidden" in checks._landing_page(_profile(field_labels=with_url, recommended_fields=("url",)))[0]["detail"]
    with patch.object(checks, "_form_level", return_value=None):
        assert checks._landing_page(_profile(field_labels=with_url, recommended_fields=("url",)))[0]["status"] == checks.OK
        not_asked = checks._landing_page(_profile(field_labels=with_url))[0]
    assert not_asked["status"] == checks.WARN and "field_level: recommended" in not_asked["fix"]
    with patch.object(checks, "_form_level", return_value={"level": "recommended", "hidden": False}):
        assert checks._landing_page(_profile(field_labels=with_url, recommended_fields=("url",)))[0]["status"] == checks.OK
