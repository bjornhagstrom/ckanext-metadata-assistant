"""The line that joins the two extensions: ai.assistant() over ckanext-ai-connector's api.client(), not patched."""

import json

import pytest

from ckanext.metadata_assistant import actions
from ckanext.metadata_assistant.llm import MetadataReviewRequest

pytestmark = [
    pytest.mark.ckan_config("ckan.plugins", "metadata_assistant ai_connector"),
    pytest.mark.usefixtures("with_plugins"),
]


def test_a_review_goes_through_the_shared_client_as_this_consumer_with_one_attempt_per_call(ai_connector_fake):
    ai_connector_fake.answers = [json.dumps({"summary": "OK", "suggestions": []})]
    spec = {"request": MetadataReviewRequest(title="Badplatser", description="Kommunens badplatser.").model_dump(mode="json")}
    result = actions.execute_review(spec)
    assert result["summary"] == "OK"
    assert [(c.consumer, c.kind, c.name) for c in ai_connector_fake.calls] == [("metadata_assistant", "structured", "metadata_review")]
    assert [client.max_attempts for client in ai_connector_fake.clients] == [1]   # the attempts are counted by the assistant


def test_each_kind_of_work_asks_for_its_own_purpose_and_the_caches_follow_its_model(ai_connector_fake):
    """API 2: the review, the translation and the landing page each ask for their purpose, so a sysadmin can give each a
    model of its own; a review or page read by another model is another cache entry."""
    from ckanext.ai_connector import purposes

    from ckanext.metadata_assistant import ai, cache

    assert set(purposes.declared()["metadata_assistant"]) == {"review", "translate", "landing_page"}
    ai_connector_fake.answers = [json.dumps({"summary": "OK", "suggestions": []})]
    actions.execute_review({"request": MetadataReviewRequest(title="Badplatser",
                                                             description="Kommunens badplatser.").model_dump(mode="json")})
    assert ai_connector_fake.purposes == ["review"]

    ai_connector_fake.models = {"review": "anthropic/review-model", "landing_page": "gemini/page-model"}
    assert ai.model(ai.REVIEW) == "anthropic/review-model" and ai.model(ai.TRANSLATE) == "gemini/fake-model"
    before = cache.review_digest({"title": "x"}, ai.model(ai.REVIEW))
    assert before != cache.review_digest({"title": "x"}, ai.model(ai.TRANSLATE))
    page_key = cache._landing_key("https://example.org/d", "sv")
    ai_connector_fake.models = {"landing_page": "anthropic/another-page-model"}
    assert cache._landing_key("https://example.org/d", "sv") != page_key


@pytest.mark.ckan_config("ckanext.ai_connector.model", "gemini/main-model")
def test_a_purpose_with_a_model_of_its_own_is_ready_while_the_main_connection_is_not(monkeypatch):
    """The connection says whether a purpose can be used; the assistant does not refuse it for the main one's sake."""
    from ckanext.ai_connector import api, purposes, settings

    from ckanext.metadata_assistant import ai

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-anthropic-key-for-the-test")
    try:
        purposes.save("metadata_assistant", "translate", "anthropic/claude-haiku-4-5", "ANTHROPIC_API_KEY")
        assert ai.problem() and ai.problem(ai.REVIEW)        # the main connection has no key
        assert ai.problem(ai.TRANSLATE) is None              # the translation's own model and key are there
        assert api.is_ready(consumer="metadata_assistant", purpose="translate")
    finally:
        purposes.forget("metadata_assistant", "translate")
        settings.forget_rows()


def test_the_ai_settings_page_names_the_assistant_and_an_older_connector_still_takes_its_purposes(monkeypatch):
    """API 3 gives the assistant's name for the page; with API 2 the purposes are declared without it."""
    from ckanext.ai_connector import purposes

    from ckanext.metadata_assistant import ai

    if ai.api.API_VERSION >= 3:   # the assistant also runs with connector 0.2 (API 2), which has no names
        ai.declare_purposes()
        assert purposes.consumer_name("metadata_assistant") == "Metadata assistant"

    seen = []
    monkeypatch.setattr(ai.api, "API_VERSION", 2)
    monkeypatch.setattr(ai.api, "declare_purposes", lambda consumer, labels: seen.append((consumer, sorted(labels))))
    ai.declare_purposes()
    assert seen == [("metadata_assistant", ["landing_page", "review", "translate"])]
