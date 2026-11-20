"""Translations (2026-09-27): suggestions, rules and provider.

Everything is a suggestion that an editor approves -- nothing is saved here.
"""

import json
import unittest
from unittest.mock import Mock, patch

from ckanext.metadata_assistant import actions
from ckanext.metadata_assistant.llm import (
    ProviderError,
    TranslationRequest,
    TranslationResponse,
)
from ckanext.ai_connector import testing
from ckanext.metadata_assistant.llm.assistant import MetadataAI
from ckanext.metadata_assistant.profiles import build_profile
from ckanext.metadata_assistant.rules import review_dataset
from ckanext.metadata_assistant.rules.translations import source_digest

SCHEMA = {
    "dataset_fields": [
        {"field_name": "title", "form_snippet": None},
        {"field_name": "title_translated", "label": "Titel", "fluent_required_language": "sv"},
        {"field_name": "notes", "form_snippet": None},
        {"field_name": "notes_translated", "label": "Beskrivning", "fluent_required_language": "sv"},
        {"field_name": "tag_string", "label": "Nyckelord"},
        {"field_name": "keywords_translated", "label": "Nyckelord (engelska)"},
        {"field_name": "theme", "label": "Tema", "choices": []},
        {"field_name": "translation_hashes",
         "translation_targets": {"title_translated": "title_translated",
                                 "notes_translated": "notes_translated",
                                 "keywords_translated": "tag_string"},
         "source_language": "sv",
         "target_languages": {"en": "recommended"},
         "translation_glossary": {"en": {"kommundel": "municipal district"}},
         "translation_instructions": {"en": "Use British English."}},
    ]
}
# What a catalogue declares in its schema's own `metadata_assistant` block (here: a stand-in).
CATALOGUE_BLOCK = {
    "name": "dcat_ap_se",
    "recommended_fields": ["tag_string", "theme", "contact_point_ids", "frequency", "spatial_coverage",
                           "temporal_coverage", "license_id", "access_rights", "data_quality", "url"],
    "guidance_markers": ["Ursprung:"],
    "translation_source": "DCAT-AP-SE, dataportal.se rek. 2",
}


def build_dcat_ap_se_profile(schema):
    return build_profile(dict(schema, metadata_assistant=CATALOGUE_BLOCK))


PROFILE = build_dcat_ap_se_profile(SCHEMA)


def prompts_default_translation():
    from ckanext.metadata_assistant import admin_settings

    return admin_settings.instructions("ai_translation_instructions")


def _codes(dataset):
    return {(f.field, f.code) for f in review_dataset(dataset, PROFILE)
            if f.code.startswith("translation_")}


class ProfileTests(unittest.TestCase):
    def test_fluent_fields_stand_for_the_core_fields(self):
        self.assertEqual(PROFILE.required_fields, ("title", "notes"))
        self.assertEqual(PROFILE.label("title"), "Titel")
        self.assertEqual(PROFILE.translation_targets["tag_string"], "keywords_translated")


class RuleTests(unittest.TestCase):
    def test_missing_english_is_information(self):
        codes = _codes({"title": "Badplatser", "title_translated": {"sv": "Badplatser"},
                        "notes": "Text.", "tag_string": "badplats"})
        self.assertIn(("title_translated", "translation_missing"), codes)
        self.assertIn(("keywords_translated", "translation_missing"), codes)

    def test_nothing_to_translate_gives_nothing(self):
        self.assertEqual(_codes({"title": "", "notes": ""}), set())

    def test_form_fields_count_as_translations(self):
        codes = _codes({"title": "Badplatser", "title_translated-en": "Bathing sites",
                        "notes": "Text.", "notes_translated-en": "Text.",
                        "tag_string": "badplats", "keywords_translated-en": "bathing site"})
        self.assertEqual(codes, set())

    def test_outdated_when_the_source_changed(self):
        dataset = {
            "title": "Kommunala badplatser",
            "title_translated": {"sv": "Kommunala badplatser", "en": "Bathing sites"},
            "notes": "Text.", "notes_translated": {"sv": "Text.", "en": "Text."},
            "translation_hashes": json.dumps({
                "title_translated": source_digest("Badplatser"),
                "notes_translated": source_digest("Text."),
            }),
        }
        codes = _codes(dataset)
        self.assertIn(("title_translated", "translation_outdated"), codes)
        self.assertNotIn(("notes_translated", "translation_outdated"), codes)

    def test_keyword_digest_ignores_order_and_case(self):
        self.assertEqual(source_digest(["Badplats", "friluftsliv"]),
                         source_digest(["friluftsliv", "badplats"]))


class TranslateActionTests(unittest.TestCase):
    @patch("ckanext.metadata_assistant.ai.assistant")
    @patch.object(actions, "get_active_profile", return_value=PROFILE)
    @patch.object(actions, "_authorized_dataset")
    def test_sends_only_the_swedish_texts_and_names_the_english_fields(
            self, authorized, _profile, from_config):
        authorized.return_value = {
            "title": "Badplatser", "notes": "Kommunens badplatser.",
            "tag_string": "badplats, friluftsliv", "private": True,
            "information_owner": "Intern uppgift",
        }
        provider = Mock()
        provider.translate.return_value = TranslationResponse(
            title="Bathing sites", description="The municipality's bathing sites.",
            keywords=["bathing site", "outdoor recreation"])
        from_config.return_value = provider

        result = actions.metadata_assistant_translate_dataset({}, {"dataset": {}})

        request = provider.translate.call_args.args[0]
        self.assertEqual(request.model_dump(), {
            "source_language": "sv", "target_language": "en", "title": "Badplatser",
            "description": "Kommunens badplatser.", "keywords": ["badplats", "friluftsliv"],
            "glossary": {"kommundel": "municipal district"},
            "instructions": "Use British English.",
            # The catalogue's instruction for translating: the default text here.
            "catalogue_instructions": prompts_default_translation()})
        by_target = {s["target_field"]: s for s in result["suggestions"]}
        self.assertEqual(by_target["title_translated"]["suggested_value"], "Bathing sites")
        self.assertEqual(by_target["keywords_translated"]["suggested_value"],
                         ["bathing site", "outdoor recreation"])
        self.assertTrue(all(s["machine_translated"] for s in result["suggestions"]))
        # The Swedish original travels with each suggestion, for comparison.
        self.assertEqual(by_target["title_translated"]["source_value"], "Badplatser")
        self.assertEqual(by_target["keywords_translated"]["source_value"], ["badplats", "friluftsliv"])
        self.assertEqual(authorized.call_args.kwargs, {"require_edit": True})

    @patch.object(actions, "get_active_profile", return_value=PROFILE)
    @patch.object(actions, "_authorized_dataset", return_value={"title": "", "notes": ""})
    def test_nothing_to_translate_is_a_clear_error(self, _authorized, _profile):
        with self.assertRaises(actions.toolkit.ValidationError):
            actions.metadata_assistant_translate_dataset({}, {"dataset": {}})

    @patch("ckanext.metadata_assistant.ai.assistant")
    @patch.object(actions, "get_active_profile", return_value=PROFILE)
    @patch.object(actions, "_authorized_dataset", return_value={"title": "Badplatser"})
    def test_provider_failure_is_a_safe_error(self, _authorized, _profile, from_config):
        provider = Mock()
        provider.translate.side_effect = ProviderError("AI-leverantören kunde inte översätta texterna.")
        from_config.return_value = provider
        with self.assertRaises(actions.toolkit.ValidationError):
            actions.metadata_assistant_translate_dataset({}, {"dataset": {}})


class ProviderTests(unittest.TestCase):
    def test_translate_uses_the_translation_prompt_and_validates(self):
        fake = testing.fake_client([{"title": "Bathing sites", "description": "", "keywords": []}])
        result = MetadataAI(fake).translate(
            TranslationRequest(source_language="sv", target_language="en", title="Badplatser", glossary={"kommundel": "municipal district"}))
        self.assertEqual(result.title, "Bathing sites")
        system, user = fake.calls[0].messages
        self.assertIn("Translate, do not improve", system["content"])
        self.assertIn("from Swedish into\nEnglish", system["content"])
        self.assertIn("kommundel: municipal district", user["content"])
        self.assertEqual((fake.calls[0].kind, fake.calls[0].name, fake.calls[0].temperature),
                         ("structured", "metadata_translation", 0.1))

    def test_the_model_must_answer_every_field(self):
        """Without `required` in the schema, the model answered with the title only."""
        schema = TranslationResponse.model_json_schema()
        self.assertEqual(sorted(schema["required"]), ["description", "keywords", "title"])

    def test_a_title_only_answer_is_rejected(self):
        provider = MetadataAI(testing.fake_client([{"title": "X"}]))
        with self.assertRaises(ProviderError):
            provider.translate(TranslationRequest(source_language="sv", target_language="en", title="Badplatser", glossary={"kommundel": "municipal district"}))

    def test_invalid_response_is_rejected(self):
        provider = MetadataAI(testing.fake_client([{"oops": 1}]))
        with self.assertRaises(ProviderError):
            provider.translate(TranslationRequest(source_language="sv", target_language="en", title="Badplatser", glossary={"kommundel": "municipal district"}))


class FieldGuidanceTests(unittest.TestCase):
    """The form's help texts are the AI's rules (2026-10-01)."""

    SCHEMA = {"dataset_fields": [
        {"field_name": "title", "form_snippet": None},
        {"field_name": "title_translated", "label": "Titel", "fluent_required_language": "sv",
         "help_text": "<span class='sk-required-lead'>Obligatoriskt</span>. Ta inte med "
                      "ortens namn. Ursprung: DCAT-AP → DCAT-AP-SE (Titel)."},
        {"field_name": "tag_string", "label": "Nyckelord",
         "help_text": "Rekommenderat. Små bokstäver. Ursprung: DCAT-AP."},
    ]}

    def test_help_text_becomes_plain_guidance_for_the_core_field(self):
        guidance = build_dcat_ap_se_profile(self.SCHEMA).field_guidance
        self.assertEqual(guidance["title"], "Obligatoriskt. Ta inte med ortens namn.")
        self.assertEqual(guidance["tag_string"], "Rekommenderat. Små bokstäver.")

    @patch("ckanext.metadata_assistant.ai.assistant")
    @patch.object(actions, "_authorized_dataset", return_value={"title": "Badplatser i kommunen"})
    def test_the_ai_review_receives_the_guidance(self, _authorized, from_config):
        from ckanext.metadata_assistant.llm import MetadataReviewResponse

        provider = Mock()
        provider.review.return_value = MetadataReviewResponse(summary="OK")
        from_config.return_value = provider
        with patch.object(actions, "get_active_profile",
                          return_value=build_dcat_ap_se_profile(self.SCHEMA)):
            actions.metadata_assistant_ai_review_dataset({}, {"dataset": {}})
        request = provider.review.call_args.args[0]
        self.assertTrue(request.field_guidance["title"].startswith("Obligatoriskt. Ta inte med ortens namn."))

    def test_the_prompt_tells_the_model_to_follow_it(self):
        from ckanext.metadata_assistant.llm.prompts import SYSTEM_PROMPT, user_prompt
        from ckanext.metadata_assistant.llm import MetadataReviewRequest

        self.assertIn("field_guidance", SYSTEM_PROMPT)
        prompt = user_prompt(MetadataReviewRequest(
            title="X", field_guidance={"title": "Ta inte med ortens namn."}))
        self.assertIn("Ta inte med ortens namn.", prompt)


class ThemeLabelTests(unittest.TestCase):
    def test_the_ai_gets_the_schema_labels_not_codes(self):
        schema = {"dataset_fields": [{"field_name": "theme", "choices": [
            {"value": "http://x/data-theme/SOCI", "label": "Befolkning och samhälle"}]}]}
        from ckanext.metadata_assistant.rules import RuleProfile

        profile = RuleProfile.from_scheming_dict("t", schema, theme_field="theme")
        self.assertEqual(profile.theme_labels["http://x/data-theme/SOCI"], "Befolkning och samhälle")


class ManyLanguagesTests(unittest.TestCase):
    """Several languages (2026-10-01): languages from the schema, any number."""

    def schema(self, **settings):
        fields = [dict(f) for f in SCHEMA["dataset_fields"]]
        fields[-1].update(settings)
        return {"dataset_fields": fields}

    def test_languages_levels_and_glossary_come_from_the_schema(self):
        profile = build_dcat_ap_se_profile(self.schema(
            target_languages={"en": "required", "fi": "optional"}))
        self.assertEqual(profile.source_language, "sv")
        self.assertEqual(dict(profile.target_languages), {"en": "required", "fi": "optional"})
        self.assertEqual(profile.translation_glossary["en"]["kommundel"], "municipal district")
        self.assertEqual(profile.translation_targets["tag_string"], "keywords_translated")

    def test_the_older_single_target_language_still_works(self):
        fields = [dict(f) for f in SCHEMA["dataset_fields"]]
        del fields[-1]["target_languages"]
        fields[-1]["target_language"] = "en"
        profile = build_dcat_ap_se_profile({"dataset_fields": fields})
        self.assertEqual(dict(profile.target_languages), {"en": "recommended"})

    def test_the_level_sets_the_severity(self):
        profile = build_dcat_ap_se_profile(self.schema(
            target_languages={"en": "required", "fi": "recommended", "se": "optional"}))
        findings = [f for f in review_dataset({"title": "Badplatser", "notes": "Text."}, profile)
                    if f.code == "translation_missing" and f.field == "title_translated"]
        self.assertEqual(sorted(f.severity for f in findings), ["error", "info"])

    def test_a_digest_without_language_is_the_first_language(self):
        dataset = {"title": "Kommunala badplatser",
                   "title_translated": {"sv": "Kommunala badplatser", "en": "Bathing sites"},
                   "translation_hashes": json.dumps({"title_translated": source_digest("Badplatser")})}
        self.assertIn(("title_translated", "translation_outdated"), _codes(dataset))

    @patch("ckanext.metadata_assistant.ai.assistant")
    @patch.object(actions, "_authorized_dataset", return_value={"title": "Badplatser"})
    def test_one_request_per_language_and_a_failure_stays_with_its_language(
            self, _authorized, from_config):
        profile = build_dcat_ap_se_profile(self.schema(
            target_languages={"en": "recommended", "fi": "recommended"}))

        def translate(request):
            if request.target_language == "fi":
                raise ProviderError("Ingen kapacitet.")
            return TranslationResponse(title="Bathing sites", description="", keywords=[])

        provider = Mock()
        provider.translate.side_effect = translate
        from_config.return_value = provider
        with patch.object(actions, "get_active_profile", return_value=profile):
            result = actions.metadata_assistant_translate_dataset({}, {"dataset": {}})

        self.assertEqual([c.args[0].target_language for c in provider.translate.call_args_list],
                         ["en", "fi"])
        self.assertEqual([s["language"] for s in result["suggestions"]], ["en"])
        self.assertEqual(result["failed"][0]["language"], "fi")

    def test_the_validator_keys_digests_by_field_and_language(self):
        from ckanext.metadata_assistant.rules.translations import translation_state_validator

        field = SCHEMA["dataset_fields"][-1]
        validator = translation_state_validator(field, {})
        data = {("title",): "Badplatser",
                ("title_translated",): json.dumps({"sv": "Badplatser", "en": "Bathing sites"}),
                ("translation_hashes",): ""}
        validator(("translation_hashes",), data, {}, {})
        self.assertEqual(json.loads(data[("translation_hashes",)]),
                         {"title_translated:en": source_digest("Badplatser")})

