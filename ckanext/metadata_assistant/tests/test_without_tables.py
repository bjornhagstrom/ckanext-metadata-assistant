"""Production runs this plugin before its tables exist (migrations 001 and 002 not run yet): the dataset
panel's AI requests and the prepared-review check must answer instead of failing."""

import pytest
from ckan import model as ckan_model

from ckanext.metadata_assistant import cache
from ckanext.metadata_assistant.model import ReviewCache, TranslationProposal
from ckanext.metadata_assistant.tests.test_jobs import (  # noqa: F401  (fixtures and helpers shared with the job tests)
    _editor_and_dataset, _start, clean_redis, provider)

pytestmark = [
    pytest.mark.ckan_config("ckan.site_id", "metadata_assistant_test"),
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "metadata_assistant ai_connector"),
    pytest.mark.usefixtures("with_plugins", "clean_db", "no_tables", "clean_redis"),
]


@pytest.fixture
def no_tables():
    for table in (ReviewCache.__table__, TranslationProposal.__table__):
        table.drop(ckan_model.meta.engine, checkfirst=True)
    ckan_model.Session.remove()
    yield  # the next test's clean_db clears the version table, so its migrate_db_for creates the tables again


def test_a_review_request_and_the_prepared_check_work_without_the_tables(provider):  # noqa: F811
    user, dataset = _editor_and_dataset()
    assert _start(user, dataset, cache_only=True) == {"state": "none"}
    answer = _start(user, dataset)
    assert answer["state"] == "done" and not answer["cached"]
    assert cache.prepared_count() == 0
