"""The contract with ckanext-ai-connector (2026-11-18): without it, with too old an API, or without its plugin, the AI is off
with a clear notice, every AI request answers with that notice (never an uncaught error), and the rule checks work."""

import importlib
import sys
from unittest.mock import patch

import pytest
from ckan.plugins import toolkit
from ckan.tests import factories

from ckanext.metadata_assistant import actions, ai, checks, jobs
from ckanext.metadata_assistant.llm import ProviderConfigurationError

pytestmark = [
    pytest.mark.ckan_config("ckan.plugins", "metadata_assistant ai_connector"),
    pytest.mark.ckan_config("ckanext.ai_connector.model", "gemini/gemini-3.5-flash-lite"),
    pytest.mark.ckan_config("ckanext.ai_connector.api_key_env", "GEMINI_API_KEY"),
    pytest.mark.usefixtures("with_plugins", "clean_db"),
]

KEY = "a-key-that-must-never-show-0001"


@pytest.fixture
def without_the_plugin(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.setattr("ckan.plugins.plugin_loaded", lambda name: name != "ai_connector")


@pytest.fixture
def without_the_package(monkeypatch):
    """ckanext-ai-connector cannot be imported (installed with pip --no-deps). ``ai`` is loaded again without it."""
    import ckanext.ai_connector

    real = sys.modules["ckanext.ai_connector.api"]
    sys.modules["ckanext.ai_connector.api"] = None   # an import of it fails
    delattr(ckanext.ai_connector, "api")
    try:
        importlib.reload(ai)
        assert ai.api is None
        yield
    finally:
        sys.modules["ckanext.ai_connector.api"] = real
        ckanext.ai_connector.api = real
        importlib.reload(ai)


@pytest.fixture
def with_an_old_api(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.setattr(ai.api, "API_VERSION", ai.MIN_API - 1)


def _rules_still_work():
    from ckanext.metadata_assistant.profiles import get_active_profile
    from ckanext.metadata_assistant.rules import review_dataset

    assert isinstance(review_dataset({"title": "x", "notes": ""}, get_active_profile()), list)


@pytest.mark.parametrize("state, words", [
    ("without_the_package", "ckanext-ai-connector, which is not installed"),
    ("with_an_old_api", "version %d of the AI connection's API" % ai.MIN_API),
    ("without_the_plugin", "the ai_connector plugin"),
])
def test_without_a_usable_connection_the_ai_is_off_with_a_notice_and_the_rules_work(state, words, request):
    request.getfixturevalue(state)
    reason = ai.problem()
    assert reason and words in reason
    assert not ai.ready()
    found = {c["key"]: c for c in checks.run_checks()}
    assert found["ai_connector"]["status"] == checks.WARN and words in found["ai_connector"]["detail"]
    assert found["database"]["key"] == "database" and "profile" in found
    _rules_still_work()


@pytest.mark.parametrize("state", ["without_the_package", "with_an_old_api", "without_the_plugin"])
def test_an_ai_request_answers_with_the_notice_and_never_an_uncaught_error(state, request):
    request.getfixturevalue(state)
    with pytest.raises(ProviderConfigurationError):
        ai.assistant()
    context = {"user": factories.Sysadmin()["name"]}

    with patch.object(actions, "prepare_translation", return_value={"kind": "translate", "sources": {}, "requests": []}):
        with pytest.raises(toolkit.ValidationError) as error:
            actions.metadata_assistant_translate_dataset(context, {"id": "x"})
    assert ai.problem() in error.value.error_dict["ai"][0]

    landing = {"kind": "landing", "url": "https://example.org/", "language": "sv"}
    with patch.object(actions, "prepare_landing_page", return_value=landing):
        with pytest.raises(toolkit.ValidationError) as error:
            actions.metadata_assistant_read_landing_page(context, {"id": "x"})
    assert ai.problem() in error.value.error_dict["ai"][0]

    # Through the job start the panel uses: the notice, and a read nobody asked for is skipped quietly.
    with patch.object(jobs, "prepare", return_value=dict(landing)):
        with pytest.raises(toolkit.ValidationError) as error:
            jobs.metadata_assistant_job_start(context, {"kind": "landing", "fresh": True})
        assert ai.problem() in error.value.error_dict["ai"][0]
        assert jobs.metadata_assistant_job_start(context, {"kind": "landing", "fresh": True, "ahead": True}) == {"state": "none"}
    assert KEY not in str(error.value)


def test_try_on_the_instructions_page_shows_the_notice(without_the_plugin, app):
    headers = {"Authorization": factories.APIToken(user=factories.Sysadmin()["name"])["token"]}
    dataset = factories.Dataset()
    page = app.post("/ckan-admin/metadata-assistant/instructions", headers=headers,
                    data={"step": "try", "dataset": dataset["name"],
                          "ai_review_instructions": "x", "ai_translation_instructions": "y"})
    assert page.status_code == 200 and "the ai_connector plugin" in page.body


@pytest.mark.parametrize("state", ["without_the_package", "with_an_old_api", "without_the_plugin"])
@pytest.mark.parametrize("queued", [False, True])
def test_the_panels_job_start_answers_with_the_notice(state, queued, request, monkeypatch):
    """What the panel calls on every opened form (cache_only) and on a click, through the real access check."""
    request.getfixturevalue(state)
    monkeypatch.setattr(jobs, "queueing", lambda: queued)
    monkeypatch.setattr(jobs, "enqueue", lambda *args, **kwargs: pytest.fail("nothing may be queued"))
    sysadmin = factories.Sysadmin()
    dataset = factories.Dataset()
    context = {"user": sysadmin["name"]}
    assert jobs.metadata_assistant_job_start(context, {"kind": "review", "id": dataset["id"], "cache_only": True}) == {"state": "none"}
    with pytest.raises(toolkit.ValidationError) as error:
        jobs.metadata_assistant_job_start(context, {"kind": "review", "id": dataset["id"]})
    assert ai.problem() in error.value.error_dict["ai"][0]


def test_try_translation_on_the_instructions_page_shows_the_notice(without_the_plugin, app):
    headers = {"Authorization": factories.APIToken(user=factories.Sysadmin()["name"])["token"]}
    dataset = factories.Dataset()
    with patch.object(actions, "prepare_translation", return_value={"kind": "translate", "sources": {}, "requests": []}):
        page = app.post("/ckan-admin/metadata-assistant/instructions", headers=headers,
                        data={"step": "try_translation", "dataset": dataset["name"],
                              "ai_review_instructions": "x", "ai_translation_instructions": "y"})
    assert page.status_code == 200 and "the ai_connector plugin" in page.body
