"""Markdown in descriptions: the setting, the plain-text fallback, the preview and the instruction to the AI."""

from types import SimpleNamespace

import pytest
from ckan.plugins import toolkit

from ckanext.metadata_assistant import actions, markdown
from ckanext.metadata_assistant.llm import MetadataReviewRequest
from ckanext.metadata_assistant.llm import prompts
from ckanext.metadata_assistant.profiles import build_profile

P = markdown.OPTION


def test_plain_text_removes_the_markup_and_keeps_the_paragraphs():
    text = "## Rubrik\n\nDet här är **viktigt** och *kursivt*.\n\n- första\n- andra\n\nSe [sidan](https://exempel.se/x) och `kod`."
    assert markdown.plain_text(text) == (
        "Rubrik\n\nDet här är viktigt och kursivt.\n\nförsta\nandra\n\nSe sidan (https://exempel.se/x) och kod.")


def test_plain_text_leaves_words_with_underscores_and_stars_inside_them_alone():
    assert markdown.plain_text("filen min_fil_namn och 2*3") == "filen min_fil_namn och 2*3"


def test_a_schema_with_a_markdown_box_is_markdown_by_default_and_the_block_can_say_otherwise():
    box = {"dataset_fields": [{"field_name": "notes_translated", "form_snippet": "fluent_markdown.html"}]}
    assert build_profile(box, source_language="sv").description_markdown is True
    assert build_profile(dict(box, metadata_assistant={"markdown": False})).description_markdown is False
    plain = {"dataset_fields": [{"field_name": "notes"}]}
    assert build_profile(plain).description_markdown is False
    assert build_profile(dict(plain, metadata_assistant={"markdown": True})).description_markdown is True


def test_the_setting_is_auto_unless_set_and_on_or_off_decide(monkeypatch):
    profile = SimpleNamespace(description_markdown=True)
    monkeypatch.delitem(toolkit.config, P, raising=False)
    assert markdown.mode() == "auto" and markdown.enabled(profile) is True
    monkeypatch.setitem(toolkit.config, P, "off")
    assert markdown.enabled(profile) is False
    monkeypatch.setitem(toolkit.config, P, "on")
    assert markdown.enabled(SimpleNamespace(description_markdown=False)) is True
    monkeypatch.setitem(toolkit.config, P, "nonsense")
    assert markdown.mode() == "auto"


def test_the_request_tells_the_ai_whether_markdown_may_be_used_and_the_default_text_explains_it():
    assert '"markdown": true' in prompts.user_prompt(MetadataReviewRequest(markdown=True))
    assert '"markdown": false' in prompts.user_prompt(MetadataReviewRequest(markdown=False))
    assert "Markdown" in prompts.DEFAULT_REVIEW_INSTRUCTIONS and "markdown: true" in prompts.DEFAULT_REVIEW_INSTRUCTIONS


def test_a_description_suggestion_is_made_plain_when_markdown_is_off_whatever_the_model_wrote():
    profile = SimpleNamespace(description_field="notes")
    result = {"summary": "s", "suggestions": [
        {"field": "notes", "suggested_value": "**Fet** text", "reason": "r"},
        {"field": "title", "suggested_value": "**Titel**", "reason": "r"}]}
    out = actions._plain_when_markdown_is_off(result, profile, allowed=False)
    assert out["suggestions"][0]["suggested_value"] == "Fet text"
    assert out["suggestions"][1]["suggested_value"] == "**Titel**"
    assert actions._plain_when_markdown_is_off(result, profile, allowed=True) is result


@pytest.mark.ckan_config("ckan.plugins", "metadata_assistant ai_connector")
@pytest.mark.usefixtures("with_plugins", "with_request_context")
def test_the_preview_is_rendered_by_ckan_and_only_for_signed_in_users():
    html = actions.metadata_assistant_render_markdown({"user": "someone"}, {"text": "**fet** <script>x</script>"})["html"]
    assert "<strong>fet</strong>" in html and "<script>" not in html
    with pytest.raises(toolkit.NotAuthorized):
        actions.metadata_assistant_render_markdown({}, {"text": "x"})


def test_blank_space_that_changes_nothing_is_taken_away_and_the_rest_is_left_alone():
    # The case from the editor: two spaces at the end of a line, then a line holding only spaces.
    assert markdown.clean_whitespace("Utegym på platsmark.  \n  \nDatamängden följer specen.  ") == (
        "Utegym på platsmark.\n\nDatamängden följer specen.")
    # Two spaces before a line that continues are a Markdown line break and stay.
    assert markdown.clean_whitespace("__Attribut__  \n+ `id` [ID]  \n+ `namn` [namn]  ") == (
        "__Attribut__  \n+ `id` [ID]  \n+ `namn` [namn]")
    assert markdown.clean_whitespace("a\r\n\r\n\r\n\r\nb\r\n") == "a\n\nb"       # line endings, and one blank line
    assert markdown.clean_whitespace("  leading spaces stay\n") == "  leading spaces stay"
    assert markdown.clean_whitespace("") == "" and markdown.clean_whitespace(None) == ""


def test_a_description_suggestion_comes_back_without_such_blank_space():
    profile = SimpleNamespace(description_field="notes")
    result = {"summary": "s", "suggestions": [
        {"field": "notes", "suggested_value": "Rad ett.  \n  \nRad två.", "reason": "r"},
        {"field": "title", "suggested_value": "Titel  ", "reason": "r"}]}
    out = actions._clean_description_whitespace(result, profile)
    assert out["suggestions"][0]["suggested_value"] == "Rad ett.\n\nRad två."
    assert out["suggestions"][1]["suggested_value"] == "Titel  "     # only the description is touched
