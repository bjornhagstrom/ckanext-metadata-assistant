"""Multilingual title, description and keywords: the validators that keep CKAN's own fields in step."""

import json
from unittest.mock import patch

import pytest
from ckan.plugins import toolkit

from ckanext.metadata_assistant import multilingual

missing = toolkit.missing


@pytest.fixture(autouse=True)
def swedish(monkeypatch):
    monkeypatch.setitem(toolkit.config, "ckan.locale_default", "sv")


def run(validator, key, data, errors=None):
    errors = errors if errors is not None else {key: []}
    validator(key, data, errors, {})
    return errors


KEY = ("title_translated",)


def test_a_call_with_only_the_plain_title_gets_it_as_the_default_language():
    data = {("title",): "Cykelpumpar"}
    run(multilingual.fluent_from_core({}, {}), KEY, data)
    assert json.loads(data[KEY]) == {"sv": "Cykelpumpar"}


def test_a_call_that_has_the_multilingual_field_is_left_alone():
    data = {KEY: '{"sv": "A", "en": "B"}', ("title",): "Other"}
    run(multilingual.fluent_from_core({}, {}), KEY, data)
    assert data[KEY] == '{"sv": "A", "en": "B"}'


def test_a_form_that_posts_the_language_boxes_is_left_alone():
    data = {("title",): "Old", ("__extras",): {"title_translated-sv": "", "title_translated-en": ""}}
    run(multilingual.fluent_from_core({}, {}), KEY, data)
    assert KEY not in data


def test_the_default_language_is_written_to_the_plain_field():
    data = {KEY: json.dumps({"sv": "Cykelpumpar", "en": "Bike pumps"})}
    run(multilingual.fluent_to_core({}, {}), KEY, data)
    assert data[("title",)] == "Cykelpumpar"


def test_the_default_language_can_be_required_while_the_others_are_not():
    data = {KEY: json.dumps({"sv": "", "en": "Bike pumps"})}
    errors = run(multilingual.fluent_to_core({"fluent_required_language": "sv"}, {}), KEY, data)
    assert errors[KEY] and ("title_translated-sv",) in errors
    data = {KEY: json.dumps({"sv": "Cykelpumpar", "en": ""})}
    assert not run(multilingual.fluent_to_core({"fluent_required_language": "sv"}, {}), KEY, data)[KEY]


def test_keywords_are_trimmed_per_language():
    assert multilingual.fluent_tags_strip('{"en": [" a", "b ", ""]}') == '{"en": ["a", "b"]}'
    assert multilingual.fluent_tags_strip({"en": [" a"]}) == {"en": ["a"]}


def test_an_empty_stored_value_does_not_crash_the_keywords_output():
    assert multilingual.fluent_tags_output("") == {}
    assert multilingual.fluent_tags_output(None) == {}
    assert multilingual.fluent_tags_output("not json") == {}
    assert multilingual.fluent_tags_output('{"en": [" a"]}') == {"en": ["a"]}


def test_the_stand_in_helper_is_registered_only_when_scheming_has_no_such_helper(monkeypatch):
    helpers = pytest.importorskip("ckanext.scheming.helpers")   # scheming is optional

    monkeypatch.setattr(helpers, "scheming_missing_required_fields", lambda *args: [], raising=False)
    assert multilingual.missing_fields_helper() == {}
    monkeypatch.delattr(helpers, "scheming_missing_required_fields")
    assert list(multilingual.missing_fields_helper()) == ["scheming_missing_required_fields"]
    assert multilingual.scheming_missing_required_fields([1, 2]) == [[], []]


@pytest.mark.usefixtures("with_plugins", "clean_db", "with_request_context")
class TestMigrate:
    """Existing text becomes the default language's version; nothing else is touched or invented."""

    def _extras(self, name):
        from ckan import model

        return dict(model.Package.get(name).extras)

    def test_it_fills_empty_multilingual_fields_and_leaves_filled_ones(self):
        from ckan.tests import factories

        factories.Dataset(name="plain", title="Cykelpumpar", notes="Pumpar i staden")
        from ckan.tests import helpers

        factories.Dataset(name="has-english", title="Bike pumps", notes="Pumps",
                          extras=[{"key": "title_translated", "value": json.dumps({"en": "Bike pumps"})}])

        with patch("ckan.lib.search.rebuild") as rebuild:
            changed = multilingual.migrate()
        assert changed == 2
        assert json.loads(self._extras("plain")["title_translated"]) == {"sv": "Cykelpumpar"}
        assert json.loads(self._extras("plain")["notes_translated"]) == {"sv": "Pumpar i staden"}
        # A dataset that already has a title_translated keeps it (only English: nothing is overwritten).
        assert json.loads(self._extras("has-english")["title_translated"]) == {"en": "Bike pumps"}
        assert json.loads(self._extras("has-english")["notes_translated"]) == {"sv": "Pumps"}
        assert rebuild.call_count == 2

    def test_a_dry_run_changes_nothing(self):
        from ckan.tests import factories

        factories.Dataset(name="plain", title="Cykelpumpar", notes="Pumpar")
        lines = []
        with patch("ckan.lib.search.rebuild") as rebuild:
            changed = multilingual.migrate(dry_run=True, echo=lines.append)
        assert changed == 1 and lines
        assert "title_translated" not in self._extras("plain")
        rebuild.assert_not_called()

    def test_running_it_twice_changes_nothing_the_second_time(self):
        from ckan.tests import factories

        factories.Dataset(name="plain", title="Cykelpumpar", notes="Pumpar")
        with patch("ckan.lib.search.rebuild"):
            assert multilingual.migrate() == 1
            assert multilingual.migrate() == 0
