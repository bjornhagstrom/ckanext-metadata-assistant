import pytest

from ckanext.ai_connector import testing


def _clear_old_ai_rows():
    """This extension's old AI rows (ckanext.metadata_assistant.ai_*, secret.*), which the migration tests write: the
    shared connection's own rows are cleared by ckanext-ai-connector's testing helper."""
    from ckan import model

    column = model.SystemInfo.key
    for prefix in ("ckanext.metadata_assistant.ai", "ckanext.metadata_assistant.secret."):
        model.Session.query(model.SystemInfo).filter(
            column.like(prefix.replace("_", r"\_") + "%", escape="\\")).delete(synchronize_session=False)
    model.Session.commit()


@pytest.fixture(scope="session", autouse=True)
def _no_rows_from_an_earlier_run():
    """CKAN applies saved options when the test app starts, before clean_db: rows left by the last test of an earlier
    run would then be in the configuration of this one. Remove them and apply the configuration again, once."""
    from ckan.lib import app_globals

    try:
        testing.clear_saved_settings()
        _clear_old_ai_rows()
        app_globals.reset()
    except Exception:
        pass   # no database yet: then there is nothing left over either
    yield


@pytest.fixture(autouse=True)
def _fresh_rows():
    """The rows read for one request are kept in flask.g, and CKAN's test plugin keeps one request open across tests:
    read them again in each test, and leave none behind for the next."""
    testing.forget_read_settings()
    yield
    try:
        testing.clear_saved_settings()
        _clear_old_ai_rows()
    except Exception:
        testing.forget_read_settings()


from ckanext.ai_connector.testing import ai_connector_fake  # noqa: E402,F401  (the shared connection's fake, as a consumer uses it)
