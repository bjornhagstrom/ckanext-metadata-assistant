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
