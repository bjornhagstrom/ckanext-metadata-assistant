"""``ckan metadata-assistant migrate-ai-settings``: the old AI connection settings and keys to ckanext-ai-connector."""

import base64
import hashlib

import pytest
from click.testing import CliRunner

from ckan import model

from ckanext.metadata_assistant import checks, migrate_ai
from ckanext.metadata_assistant.cli import metadata_assistant

OLD = migrate_ai.OLD
NEW = migrate_ai.NEW
PORTAL_SECRET = "a-portal-secret-for-the-tests"
OLD_KEY = "AIzaSy-a-key-from-the-old-page-0042"
ACME_KEY = "acme-a-key-for-another-service-0043"

pytestmark = [
    pytest.mark.ckan_config("ckan.plugins", "metadata_assistant ai_connector"),
    pytest.mark.ckan_config("SECRET_KEY", PORTAL_SECRET),
    pytest.mark.usefixtures("with_plugins", "clean_db"),
]


def _old_token(value):
    from cryptography.fernet import Fernet

    derived = hashlib.sha256(b"ckanext-metadata-assistant api key\0" + PORTAL_SECRET.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived)).encrypt(value.encode()).decode()


def _old_rows():
    model.set_system_info(OLD + "ai_model", "anthropic/saved-on-the-old-page")
    model.set_system_info(OLD + "ai_timeout_seconds", "45")
    model.set_system_info(OLD + "ai_url_context_timeout_seconds", "200")
    model.set_system_info(OLD + "ai_provider", "litellm")
    model.set_system_info(OLD + "ai_custom_key_names", '["ACME_API_KEY"]')
    model.set_system_info(OLD + "secret.GEMINI_API_KEY", _old_token(OLD_KEY))
    model.set_system_info(OLD + "secret.ACME_API_KEY", _old_token(ACME_KEY))


def _run(*args):
    result = CliRunner().invoke(metadata_assistant, ["migrate-ai-settings", *args])
    assert result.exit_code == 0, result.output
    return result.output


def test_the_old_values_and_keys_are_moved_once_and_no_value_is_printed():
    from ckanext.ai_connector import keys, settings

    _old_rows()
    assert "would copy %smodel" % NEW in _run("--dry-run")
    assert model.get_system_info(NEW + "model") is None

    output = _run()
    for value in (OLD_KEY, ACME_KEY, "saved-on-the-old-page", "45", "200"):
        assert value not in output
    assert model.get_system_info(NEW + "model") == "anthropic/saved-on-the-old-page"
    assert model.get_system_info(NEW + "timeout_seconds") == "45"
    assert model.get_system_info(NEW + "page_read_timeout_seconds") == "200"
    assert model.get_system_info(NEW + "provider") is None   # no longer an option
    settings.forget_rows()
    assert keys.custom_key_names() == ["ACME_API_KEY"]
    assert keys.stored_key("GEMINI_API_KEY") == OLD_KEY and keys.stored_key("ACME_API_KEY") == ACME_KEY
    assert model.get_system_info(NEW + "secret.GEMINI_API_KEY").startswith("v1:")
    assert model.get_system_info(OLD + "ai_model") is not None   # the old rows stay without --remove-old

    assert "nothing is copied again" in _run()   # again: nothing new


def test_a_value_already_saved_under_the_new_name_is_kept():
    _old_rows()
    model.set_system_info(NEW + "model", "gemini/chosen-on-the-new-page")
    _run()
    assert model.get_system_info(NEW + "model") == "gemini/chosen-on-the-new-page"


def test_remove_old_only_deletes_the_old_rows_after_the_move_and_the_check_then_is_quiet():
    _old_rows()
    result = CliRunner().invoke(metadata_assistant, ["migrate-ai-settings", "--remove-old"])
    assert result.exit_code != 0 and "without --remove-old first" in result.output   # not before the move
    assert model.get_system_info(OLD + "ai_model") is not None

    _run()
    check = next(c for c in checks.run_checks() if c["key"] == "ai_migration")
    assert check["fix"].endswith("migrate-ai-settings --remove-old")   # only the old rows wait
    output = _run("--remove-old")
    assert "removed %ssecret.GEMINI_API_KEY" % OLD in output and "copied" not in output
    for key in ("ai_model", "ai_custom_key_names", "secret.GEMINI_API_KEY", "ai_provider"):
        assert model.get_system_info(OLD + key) is None
    assert migrate_ai.moved() is not None   # the mark stays
    assert "ai_migration" not in {c["key"] for c in checks.run_checks()}


def test_a_second_run_never_brings_back_what_was_removed_or_reset_on_the_new_page():
    from ckanext.ai_connector import keys, settings

    _old_rows()
    _run()
    settings.forget_rows()
    keys.remove_key("GEMINI_API_KEY")
    keys.remove_custom_key("ACME_API_KEY")
    settings.reset()
    settings.forget_rows()

    output = _run()
    assert "nothing is copied again" in output and "copied" not in output.replace("copied again", "")
    _run("--remove-old")
    for key in ("model", "timeout_seconds", "secret.GEMINI_API_KEY", "secret.ACME_API_KEY"):
        assert model.get_system_info(NEW + key) is None, key
    settings.forget_rows()
    assert keys.custom_key_names() == []


def test_a_key_that_cannot_be_read_stops_the_move_and_nothing_is_written():
    model.set_system_info(OLD + "ai_model", "anthropic/saved-on-the-old-page")
    model.set_system_info(OLD + "secret.GEMINI_API_KEY", "not-a-token")
    result = CliRunner().invoke(metadata_assistant, ["migrate-ai-settings"])
    assert result.exit_code != 0 and "GEMINI_API_KEY" in result.output and "Enter it again" in result.output
    assert model.get_system_info(OLD + "secret.GEMINI_API_KEY") == "not-a-token"
    assert model.get_system_info(NEW + "model") is None and migrate_ai.moved() is None


@pytest.mark.ckan_config(OLD + "ai_model", "gemini/an-old-server-option")
@pytest.mark.ckan_config(OLD + "ai_url_context_timeout_seconds", "200")
def test_old_server_options_are_named_with_their_new_names():
    output = _run()
    assert "rename CKANEXT__METADATA_ASSISTANT__AI_MODEL to CKANEXT__AI_CONNECTOR__MODEL" in output
    assert "CKANEXT__METADATA_ASSISTANT__AI_URL_CONTEXT_TIMEOUT_SECONDS to CKANEXT__AI_CONNECTOR__PAGE_READ_TIMEOUT_SECONDS" in output
    assert "an-old-server-option" not in output


def test_a_key_stored_by_the_development_version_of_ai_connector_is_encrypted_again():
    """For a few days ckanext-ai-connector stored keys with this extension's old cipher and no version prefix."""
    from ckanext.ai_connector import keys, settings

    model.set_system_info(NEW + "secret.GEMINI_API_KEY", _old_token(OLD_KEY))
    model.set_system_info(NEW + "url_context_timeout_seconds", "150")
    _run()
    settings.forget_rows()
    assert model.get_system_info(NEW + "secret.GEMINI_API_KEY").startswith("v1:")
    assert keys.stored_key("GEMINI_API_KEY") == OLD_KEY
    assert model.get_system_info(NEW + "page_read_timeout_seconds") == "150"


def test_remove_old_removes_the_old_key_in_one_run_also_beside_a_key_of_the_development_version():
    """A stack that ran the development version has the key twice: under the old name and, without "v1:", under the new."""
    model.set_system_info(OLD + "secret.GEMINI_API_KEY", _old_token(OLD_KEY))
    model.set_system_info(NEW + "secret.GEMINI_API_KEY", _old_token(OLD_KEY))
    _run()
    assert model.get_system_info(NEW + "secret.GEMINI_API_KEY").startswith("v1:")
    _run("--remove-old")
    assert model.get_system_info(OLD + "secret.GEMINI_API_KEY") is None
    assert "ai_migration" not in {c["key"] for c in checks.run_checks()}
