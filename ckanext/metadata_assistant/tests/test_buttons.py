"""CKAN 2.12 runs Bootstrap 5, which has no `btn-default`: a button with only that class shows as plain text (2026-10-29: "Use suggestion" could not be seen)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_button_of_the_review_panel_is_styled_with_the_missing_btn_default_class():
    files = [ROOT / "assets" / "js" / "review.js", ROOT / "templates" / "metadata_assistant" / "snippets" / "review_panel.html"]
    assert [str(f.name) for f in files if "btn-default" in f.read_text()] == []


def test_the_use_suggestion_button_is_a_primary_button():
    text = (ROOT / "assets" / "js" / "review.js").read_text()
    assert text.count("apply.className = 'btn btn-primary metadata-assistant-review__apply'") == 2


def test_the_form_asks_what_to_do_with_suggestions_that_were_not_used():
    text = (ROOT / "assets" / "js" / "review.js").read_text()
    assert "guardUnusedSuggestions(form);" in text and "unused_save" in text and "unused_discard" in text

