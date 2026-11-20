"""Unit tests for the dependency-free part of profiles.py (``build_profile``).

``build_profile`` takes an already-parsed schema dict and needs neither PyYAML nor a running CKAN
instance. Which profile applies for a portal (file, Scheming or CKAN's own fields) needs CKAN's
config and is covered in test_profile_selection.py.
"""

import unittest

from ckanext.metadata_assistant.profiles import build_profile, ckan_core_schema
from ckanext.metadata_assistant.rules import review_dataset

ENVI = "http://publications.europa.eu/resource/authority/data-theme/ENVI"
SOCI = "http://publications.europa.eu/resource/authority/data-theme/SOCI"

# A small stand-in for a catalogue's schema.
SAMPLE_SCHEMA = {
    "metadata_assistant": {
        "name": "sample",
        "recommended_fields": ["tag_string", "theme", "license_id"],
        "translation_source": "The sample guidelines",
    },
    "dataset_fields": [
        {"field_name": "title", "label": "Titel", "required": True},
        {"field_name": "notes", "label": "Beskrivning", "required": True},
        {"field_name": "publisher_actor_id", "label": "Utgivare", "required": True},
        {"field_name": "owner_org", "label": "Organisation i katalogen", "required": True},
        {"field_name": "tag_string", "label": "Nyckelord"},
        {
            "field_name": "theme",
            "label": "Tema",
            "choices": [{"value": ENVI, "label": "Miljö"}, {"value": SOCI, "label": "Befolkning och samhälle"}],
        },
        {"field_name": "license_id", "label": "Licens"},
    ],
}


class BuildProfileTests(unittest.TestCase):
    def test_required_fields_come_from_the_schema(self):
        self.assertEqual(
            set(build_profile(SAMPLE_SCHEMA).required_fields),
            {"title", "notes", "publisher_actor_id", "owner_org"},
        )

    def test_the_catalogue_declares_its_name_and_recommended_fields(self):
        profile = build_profile(SAMPLE_SCHEMA)
        self.assertEqual(profile.name, "sample")
        self.assertEqual(profile.recommended_fields, ("tag_string", "theme", "license_id"))
        self.assertEqual(profile.translation_source, "The sample guidelines")

    def test_theme_vocabulary_comes_from_the_schema_choices(self):
        self.assertEqual(build_profile(SAMPLE_SCHEMA).theme_allowed_values, {ENVI, SOCI})

    def test_profile_is_usable_end_to_end_with_the_rule_engine(self):
        dataset = {
            "title": "",  # missing required field
            "notes": "En tillräckligt lång beskrivning för att undvika den varningen.",
            "publisher_actor_id": "actor-1",
            "owner_org": "an-org",
            "theme": ["not-a-real-theme"],  # invalid vocabulary value
        }
        codes = {f.code for f in review_dataset(dataset, build_profile(SAMPLE_SCHEMA))}
        self.assertIn("required_field_missing", codes)
        self.assertIn("theme_not_in_vocabulary", codes)
        self.assertIn("recommended_field_missing", codes)  # tag_string, license_id

    def test_without_a_block_recommended_fields_follow_field_level(self):
        schema = {"dataset_fields": [
            {"field_name": "title", "required": True},
            {"field_name": "tag_string", "field_level": "recommended"},
            {"field_name": "frequency", "field_level": "recommended"},
            {"field_name": "title_translated", "field_level": "recommended"},
            {"field_name": "license_id"},
        ]}
        self.assertEqual(build_profile(schema).recommended_fields, ("tag_string", "frequency"))

    def test_without_anything_declared_a_small_default_applies_to_the_fields_the_schema_has(self):
        schema = {"dataset_fields": [
            {"field_name": "title", "required": True},
            {"field_name": "tag_string"},
            {"field_name": "license_id"},
            {"field_name": "something_else"},
        ]}
        profile = build_profile(schema)
        self.assertEqual(profile.recommended_fields, ("tag_string", "license_id"))
        self.assertEqual(profile.keywords_field, "tag_string")
        self.assertEqual(profile.license_field, "license_id")
        self.assertIsNone(profile.theme_field)

    def test_nothing_about_a_particular_catalogue_is_built_in(self):
        profile = build_profile({"dataset_fields": [{"field_name": "title", "required": True}]})
        self.assertEqual(profile.name, "schema")
        self.assertEqual(profile.translation_source, "")
        self.assertEqual(profile.recommended_fields, ())


class GuidanceMarkerTests(unittest.TestCase):
    SCHEMA = {"dataset_fields": [
        {"field_name": "tag_string", "help_text": "<b>Small</b> letters. Note: for the editor only."},
    ]}

    def test_help_text_is_kept_whole_unless_the_catalogue_names_a_marker(self):
        self.assertEqual(build_profile(self.SCHEMA).field_guidance["tag_string"],
                         "Small letters. Note: for the editor only.")

    def test_help_text_ends_at_the_catalogues_marker(self):
        schema = dict(self.SCHEMA, metadata_assistant={"guidance_markers": ["Note:"]})
        self.assertEqual(build_profile(schema).field_guidance["tag_string"], "Small letters.")


class FluentTranslationTests(unittest.TestCase):
    """A schema with multilingual fields needs no translation block."""

    SCHEMA = {"dataset_fields": [
        {"field_name": "title", "form_snippet": None},
        {"field_name": "title_translated", "preset": "fluent_core_translated", "form_languages": ["sv", "en"]},
        {"field_name": "notes_translated", "preset": "fluent_text", "form_languages": ["sv", "en"]},
        {"field_name": "tag_string"},
        {"field_name": "keywords_translated", "preset": "fluent_tags", "form_languages": ["en"]},
    ]}

    def test_targets_and_languages_are_read_from_the_fields(self):
        profile = build_profile(self.SCHEMA, source_language="sv")
        self.assertEqual(profile.translation_targets,
                         {"title": "title_translated", "notes": "notes_translated",
                          "tag_string": "keywords_translated"})
        self.assertEqual(profile.source_language, "sv")
        self.assertEqual(dict(profile.target_languages), {"en": "optional"})

    def test_a_fluent_field_without_the_suffix_is_not_derived(self):
        schema = {"dataset_fields": [
            {"field_name": "title", "preset": "fluent_core_translated", "form_languages": ["sv", "en"]},
            {"field_name": "tag_string"}]}
        self.assertEqual(build_profile(schema, source_language="sv").translation_targets, {})

    def test_without_a_source_language_nothing_is_derived(self):
        self.assertEqual(build_profile(self.SCHEMA).translation_targets, {})

    def test_an_explicit_translation_block_wins(self):
        schema = {"dataset_fields": self.SCHEMA["dataset_fields"] + [
            {"field_name": "translation_hashes",
             "translation_targets": {"title_translated": "title_translated"},
             "source_language": "sv", "target_languages": {"de": "required"}}]}
        profile = build_profile(schema, source_language="en")
        self.assertEqual(dict(profile.target_languages), {"de": "required"})
        self.assertEqual(profile.source_language, "sv")


class CkanCoreProfileTests(unittest.TestCase):
    def test_a_portal_without_a_schema_is_reviewed_on_ckans_own_fields(self):
        profile = build_profile(ckan_core_schema())
        self.assertEqual(profile.name, "ckan_core")
        self.assertEqual(profile.required_fields, ("title",))
        self.assertEqual(profile.recommended_fields, ("tag_string", "license_id", "url"))
        findings = review_dataset({"title": "Bike pumps", "notes": ""}, profile)
        self.assertIn("recommended_field_missing", {f.code for f in findings})


if __name__ == "__main__":
    unittest.main()


class BaselineGuidanceTests(unittest.TestCase):
    """A schema with no help texts still gives the AI the same starting point."""

    SCHEMA = {"dataset_fields": [
        {"field_name": "title", "required": True},
        {"field_name": "notes"},
        {"field_name": "tag_string"},
        {"field_name": "something_else"},
    ]}

    def test_fields_without_help_text_get_the_baseline(self):
        guidance = build_profile(self.SCHEMA).field_guidance
        self.assertEqual(set(guidance), {"title", "notes", "tag_string"})
        self.assertIn("publisher", guidance["title"])

    def test_the_schemas_own_help_text_replaces_the_baseline(self):
        schema = {"dataset_fields": [
            {"field_name": "title", "help_text": "Our own rule."}, {"field_name": "notes"}]}
        guidance = build_profile(schema).field_guidance
        self.assertEqual(guidance["title"], "Our own rule.")
        self.assertIn("Describe the content", guidance["notes"])

    def test_a_multilingual_field_counts_as_its_core_field(self):
        schema = {"dataset_fields": [{"field_name": "title_translated"}]}
        self.assertIn("title", build_profile(schema).field_guidance)

    def test_a_field_the_schema_does_not_have_gets_nothing(self):
        self.assertNotIn("url", build_profile(self.SCHEMA).field_guidance)

    def test_theme_guidance_needs_a_theme_field(self):
        schema = {"dataset_fields": [{"field_name": "theme", "choices": [{"value": "a", "label": "A"}]}]}
        self.assertIn("theme", build_profile(schema).field_guidance)

    def test_a_catalogue_can_turn_the_baseline_off(self):
        schema = dict(self.SCHEMA, metadata_assistant={"baseline_guidance": False})
        self.assertEqual(build_profile(schema).field_guidance, {})

    def test_nothing_about_a_particular_catalogue_is_in_the_baseline(self):
        from ckanext.metadata_assistant.guidance import BASELINE_GUIDANCE

        text = " ".join(BASELINE_GUIDANCE.values()).lower()
        for word in ("skellefte", "dataportal", "sala", "uppsala", "kommun"):
            self.assertNotIn(word, text)


class LocalisedLabelTests(unittest.TestCase):
    """A schema may label a field per language; a finding must show text, never the map."""

    SCHEMA = {"dataset_fields": [
        {"field_name": "title", "label": {"en": "Title", "sv": "Titel", "sv_SE": "Titel"}, "required": True},
        {"field_name": "notes", "label": {"en": "Description"}},
        {"field_name": "tag_string", "label": {"de": "Schlagwörter"}},
    ]}

    def test_the_label_follows_the_pages_language(self):
        from unittest.mock import patch

        profile = build_profile(self.SCHEMA)
        for language, expected in (("sv", "Titel"), ("sv_SE", "Titel"), ("en", "Title"), ("fr", "Title")):
            with patch("ckanext.metadata_assistant.localization.ui_language", return_value=language):
                self.assertEqual(profile.label("title"), expected, language)

    def test_a_language_with_no_match_falls_back_to_english_then_to_any(self):
        from unittest.mock import patch

        profile = build_profile(self.SCHEMA)
        with patch("ckanext.metadata_assistant.localization.ui_language", return_value="sv"):
            self.assertEqual(profile.label("notes"), "Description")
            self.assertEqual(profile.label("tag_string"), "Schlagwörter")

    def test_a_finding_names_the_field_in_words(self):
        findings = review_dataset({"title": "", "notes": ""}, build_profile(self.SCHEMA))
        for finding in findings:
            self.assertNotIn("{", finding.message)
