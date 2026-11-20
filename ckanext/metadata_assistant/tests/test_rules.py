"""Unit tests for the deterministic rule engine.

Dependency-free by design: no CKAN, no Docker, no network. Run with:

    python3 -m unittest discover -s ckanext/metadata_assistant/tests -v

from the ckanext-metadata-assistant directory, or via ``node``-style CI
steps that just invoke ``python3 -m unittest``.
"""

import unittest

from ckanext.metadata_assistant.rules.engine import review_dataset
from ckanext.metadata_assistant.rules.profile import RuleProfile


THEME_A = "http://publications.europa.eu/resource/authority/data-theme/ENVI"
THEME_B = "http://publications.europa.eu/resource/authority/data-theme/SOCI"


def make_profile(**overrides) -> RuleProfile:
    defaults = dict(
        name="test-profile",
        description_tip_words=0,  # the tip has its own tests
        required_fields=("title", "notes", "owner_org"),
        recommended_fields=("tag_string", "theme", "license_id"),
        field_labels={
            "title": "Titel",
            "notes": "Beskrivning",
            "owner_org": "Organisation",
            "tag_string": "Nyckelord",
            "theme": "Tema",
            "license_id": "Licens",
        },
        theme_field="theme",
        theme_allowed_values=frozenset({THEME_A, THEME_B}),
        keywords_field="tag_string",
        title_field="title",
        description_field="notes",
        license_field="license_id",
        min_description_words=8,
    )
    defaults.update(overrides)
    return RuleProfile(**defaults)


GOOD_DATASET = {
    "title": "Befolkningsprognos per kommundel 2025-2035",
    "notes": (
        "Årlig prognos över invånare per åldersgrupp och kommundel. "
        "Kommunen använder den som planeringsunderlag för skola och omsorg."
    ),
    "owner_org": "example-org",
    "tag_string": "befolkning, prognos, kommundel",
    "theme": [THEME_B],
    "license_id": "cc-by",
}


def findings_by_code(findings):
    return {f.code for f in findings}


class RequiredFieldsTests(unittest.TestCase):
    def test_no_findings_for_a_complete_dataset(self):
        findings = review_dataset(GOOD_DATASET, make_profile())
        self.assertEqual(findings, [])

    def test_missing_required_field_is_an_error(self):
        dataset = dict(GOOD_DATASET, title="")
        findings = review_dataset(dataset, make_profile())
        errors = [f for f in findings if f.severity == "error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].code, "required_field_missing")
        self.assertEqual(errors[0].field, "title")
        self.assertIn("Titel", errors[0].message)

    def test_whitespace_only_value_counts_as_missing(self):
        dataset = dict(GOOD_DATASET, title="   ")
        findings = review_dataset(dataset, make_profile())
        self.assertIn("required_field_missing", findings_by_code(findings))

    def test_missing_recommended_field_is_a_warning_not_an_error(self):
        dataset = dict(GOOD_DATASET, license_id="")
        findings = review_dataset(dataset, make_profile())
        matching = [f for f in findings if f.code == "recommended_field_missing"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].severity, "warning")
        self.assertEqual(matching[0].field, "license_id")

    def test_required_field_is_not_also_reported_as_recommended(self):
        profile = make_profile(
            required_fields=("title",), recommended_fields=("title", "notes")
        )
        dataset = dict(GOOD_DATASET, title="")
        findings = review_dataset(dataset, profile)
        title_findings = [f for f in findings if f.field == "title"]
        self.assertEqual(len(title_findings), 1)
        self.assertEqual(title_findings[0].code, "required_field_missing")


class ThemeVocabularyTests(unittest.TestCase):
    def test_theme_outside_vocabulary_is_an_error(self):
        dataset = dict(GOOD_DATASET, theme=["not-a-real-theme"])
        findings = review_dataset(dataset, make_profile())
        matching = [f for f in findings if f.code == "theme_not_in_vocabulary"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].severity, "error")

    def test_theme_as_a_single_string_is_also_checked(self):
        dataset = dict(GOOD_DATASET, theme="not-a-real-theme")
        findings = review_dataset(dataset, make_profile())
        self.assertIn("theme_not_in_vocabulary", findings_by_code(findings))

    def test_profile_without_theme_field_skips_the_check(self):
        profile = make_profile(theme_field=None, theme_allowed_values=frozenset())
        dataset = dict(GOOD_DATASET, theme=["anything"])
        findings = review_dataset(dataset, profile)
        self.assertNotIn("theme_not_in_vocabulary", findings_by_code(findings))


class KeywordTests(unittest.TestCase):
    def test_duplicate_keywords_are_flagged(self):
        dataset = dict(GOOD_DATASET, tag_string="befolkning, prognos, Befolkning")
        findings = review_dataset(dataset, make_profile())
        matching = [f for f in findings if f.code == "duplicate_keywords"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].severity, "warning")

    def test_a_single_long_phrase_is_flagged_as_not_separated(self):
        dataset = dict(
            GOOD_DATASET,
            tag_string="befolkningsprognos för kommundelar och åldersgrupper 2025",
        )
        findings = review_dataset(dataset, make_profile())
        self.assertIn("keywords_not_separated", findings_by_code(findings))

    def test_normal_comma_separated_keywords_are_not_flagged(self):
        findings = review_dataset(GOOD_DATASET, make_profile())
        self.assertNotIn("keywords_not_separated", findings_by_code(findings))
        self.assertNotIn("duplicate_keywords", findings_by_code(findings))


class DescriptionTests(unittest.TestCase):
    def test_description_identical_to_title_is_flagged(self):
        dataset = dict(GOOD_DATASET, notes=GOOD_DATASET["title"])
        findings = review_dataset(dataset, make_profile())
        matching = [f for f in findings if f.code == "description_repeats_title"]
        self.assertEqual(len(matching), 1)

    def test_description_identical_to_title_ignoring_case_and_spacing(self):
        dataset = dict(
            GOOD_DATASET,
            notes="  BEFOLKNINGSPROGNOS   PER KOMMUNDEL 2025-2035.  ",
        )
        findings = review_dataset(dataset, make_profile())
        self.assertIn("description_repeats_title", findings_by_code(findings))

    def test_very_short_description_is_flagged(self):
        dataset = dict(GOOD_DATASET, notes="Kort text.")
        findings = review_dataset(dataset, make_profile())
        self.assertIn("description_too_short", findings_by_code(findings))

    def test_missing_description_does_not_trigger_content_checks(self):
        # Absence is the required-field check's job; content checks should
        # not also fire and produce a confusing double message.
        dataset = dict(GOOD_DATASET, notes="")
        findings = review_dataset(dataset, make_profile())
        codes = findings_by_code(findings)
        self.assertIn("required_field_missing", codes)
        self.assertNotIn("description_repeats_title", codes)
        self.assertNotIn("description_too_short", codes)


class LicenseInDescriptionTests(unittest.TestCase):
    def test_license_url_in_description_with_empty_license_field_is_flagged(self):
        dataset = dict(
            GOOD_DATASET,
            license_id="",
            notes=(
                GOOD_DATASET["notes"]
                + " Licens: https://creativecommons.org/licenses/by/4.0/"
            ),
        )
        findings = review_dataset(dataset, make_profile())
        self.assertIn("license_info_in_wrong_field", findings_by_code(findings))

    def test_license_url_in_description_is_fine_if_license_field_is_also_set(self):
        dataset = dict(
            GOOD_DATASET,
            notes=(
                GOOD_DATASET["notes"]
                + " Licens: https://creativecommons.org/licenses/by/4.0/"
            ),
        )
        findings = review_dataset(dataset, make_profile())
        self.assertNotIn("license_info_in_wrong_field", findings_by_code(findings))

    def test_unrelated_mention_of_licensing_is_not_flagged(self):
        dataset = dict(
            GOOD_DATASET,
            license_id="",
            notes=GOOD_DATASET["notes"] + " Se vår licenspolicy för mer information.",
        )
        findings = review_dataset(dataset, make_profile())
        self.assertNotIn("license_info_in_wrong_field", findings_by_code(findings))


class OrderingTests(unittest.TestCase):
    def test_errors_are_sorted_before_warnings(self):
        dataset = dict(GOOD_DATASET, title="", license_id="")
        findings = review_dataset(dataset, make_profile())
        severities = [f.severity for f in findings]
        self.assertEqual(severities, sorted(severities, key=lambda s: {"error": 0, "warning": 1, "info": 2}[s]))
        self.assertEqual(severities[0], "error")


class FromSchemingDictTests(unittest.TestCase):
    def test_builds_a_profile_from_a_scheming_shaped_schema(self):
        schema = {
            "dataset_fields": [
                {"field_name": "title", "label": "Titel", "required": True},
                {"field_name": "notes", "label": "Beskrivning", "required": True},
                {
                    "field_name": "theme",
                    "label": "Tema",
                    "choices": [
                        {"value": THEME_A, "label": "Miljö"},
                        {"value": THEME_B, "label": "Befolkning och samhälle"},
                    ],
                },
                {"field_name": "tag_string", "label": "Nyckelord"},
            ]
        }
        profile = RuleProfile.from_scheming_dict(
            "dcat_ap_se",
            schema,
            recommended_fields=["tag_string", "theme"],
            theme_field="theme",
        )
        self.assertEqual(profile.required_fields, ("title", "notes"))
        self.assertEqual(profile.theme_allowed_values, frozenset({THEME_A, THEME_B}))
        self.assertEqual(profile.label("theme"), "Tema")
        self.assertEqual(profile.label("unknown_field"), "unknown_field")

        dataset = {"title": "", "notes": "x" * 50, "theme": ["not-allowed"]}
        findings = review_dataset(dataset, profile)
        self.assertIn("required_field_missing", findings_by_code(findings))
        self.assertIn("theme_not_in_vocabulary", findings_by_code(findings))


if __name__ == "__main__":
    unittest.main()


class DataServiceTests(unittest.TestCase):
    """An API without a data service, and a data service on a file (rules/data_services.py)."""

    def _codes(self, *resources, field="access_services"):
        profile = make_profile(service_field=field)
        dataset = {"title": "T", "resources": list(resources)}
        return [f.code for f in review_dataset(dataset, profile) if f.code in ("api_without_service", "service_on_file")]

    def test_addresses_formats_and_specifications_that_say_api(self):
        for resource in (
            {"url": "https://example.org/api/v1/addresses"},
            {"url": "https://example.org/geoserver/wfs?service=WFS&request=GetFeature"},
            {"url": "https://example.org/arcgis/rest/services/Parks/FeatureServer"},
            {"url": "https://example.org/data", "format": "WMS"},
            {"url": "https://example.org/data", "conforms_to": ["https://example.org/openapi.json"]},
        ):
            self.assertEqual(self._codes(resource), ["api_without_service"], resource)

    def test_files_and_pages_are_not_apis(self):
        for resource in (
            {"url": "https://example.org/api/export/parks.csv"},
            {"url": "https://example.org/files/data.zip", "format": "ZIP"},
            {"url": "https://example.org/about-the-data"},
            {"url": "https://example.org/rapid/report"},
            {"url": ""},
        ):
            self.assertEqual(self._codes(resource), [], resource)

    def test_an_api_with_a_data_service_is_fine_in_both_stored_forms(self):
        service = {"title": "Adress-API", "endpoint_url": ["https://example.org/api"]}
        self.assertEqual(self._codes({"url": "https://example.org/api", "access_services": [service]}), [])
        import json
        self.assertEqual(self._codes({"url": "https://example.org/api", "access_services": json.dumps([service])}), [])

    def test_an_api_with_a_service_from_the_registry_is_a_data_service_too(self):
        # ckanext-data-service-registry: the distribution points at services by id (a list, or the JSON text CKAN stores)
        for ids in (["3f1c"], '["3f1c"]'):
            self.assertEqual(self._codes({"url": "https://example.org/api", "access_service_ids": ids}), [], ids)
        self.assertEqual(self._codes({"url": "https://example.org/api", "access_service_ids": []}), ["api_without_service"])

    def test_a_registry_service_is_judged_for_contact_like_an_embedded_one(self):
        profile = make_profile(service_field="access_services")
        dataset = {"title": "T", "hvd_category": ["x"], "resources": [{"url": "https://example.org/api", "access_service_ids": ["3f1c"]}]}
        self.assertIn("hvd_service_without_contact", [f.code for f in review_dataset(dataset, profile)])
        dataset["contact_email"] = "a@b.se"
        self.assertNotIn("hvd_service_without_contact", [f.code for f in review_dataset(dataset, profile)])

    def test_a_data_service_on_a_plain_file_is_noted(self):
        resource = {"url": "https://example.org/a.csv", "access_services": [{"title": "X"}]}
        self.assertEqual(self._codes(resource), ["service_on_file"])

    def test_nothing_is_checked_without_a_service_field_in_the_schema(self):
        dataset = {"title": "T", "resources": [{"url": "https://example.org/api/x"}]}
        self.assertNotIn("api_without_service", [f.code for f in review_dataset(dataset, make_profile())])

    def _contact_codes(self, dataset_fields, service):
        profile = make_profile(service_field="access_services")
        dataset = dict({"title": "T", "hvd_category": ["http://data.europa.eu/bna/c_ac64a52d"],
                        "resources": [{"url": "https://example.org/api", "access_services": [service]}]}, **dataset_fields)
        return [f for f in review_dataset(dataset, profile) if f.code == "hvd_service_without_contact"]

    def test_an_hvd_service_without_any_contact_is_an_error(self):
        found = self._contact_codes({}, {"title": "API"})
        self.assertEqual([f.severity for f in found], ["error"])

    def test_a_contact_on_the_dataset_or_the_service_is_enough(self):
        for fields, service in (({"contact_point_ids": ["a"]}, {"title": "API"}), ({"contact_email": "a@b.se"}, {"title": "API"}),
                                ({}, {"title": "API", "contact_email": "a@b.se"})):
            self.assertEqual(self._contact_codes(fields, service), [], (fields, service))

    def test_every_service_needs_a_contact_when_the_dataset_has_none(self):
        profile = make_profile(service_field="access_services")
        api = {"url": "https://example.org/api"}
        dataset = {"title": "T", "hvd_category": ["x"], "resources": [
            dict(api, access_services=[{"title": "A", "contact_email": "a@b.se"}]),
            dict(api, access_services=[{"title": "B"}])]}
        self.assertIn("hvd_service_without_contact", [f.code for f in review_dataset(dataset, profile)])

    def test_text_that_is_no_e_mail_address_is_no_contact(self):
        self.assertEqual(len(self._contact_codes({}, {"title": "API", "contact_email": "Kundtjänst"})), 1)
        self.assertEqual(len(self._contact_codes({}, {"title": "API", "contact_email": "kontakt api@x.se"})), 1)

    def test_each_of_the_datasets_contact_fields_counts(self):
        for field in ("contact_name", "maintainer", "maintainer_email", "author_email", "contact_uri"):
            self.assertEqual(self._contact_codes({field: "x"}, {"title": "API"}), [], field)

    def test_the_actor_registry_is_a_tip_whether_or_not_it_is_installed(self):
        from unittest import mock

        with mock.patch("ckanext.metadata_assistant.rules.data_services._actor_registry_installed", return_value=True):
            tip = self._contact_codes({}, {"title": "API"})[0].message
        with mock.patch("ckanext.metadata_assistant.rules.data_services._actor_registry_installed", return_value=False):
            plain = self._contact_codes({}, {"title": "API"})[0].message
        self.assertIn("choose a contact point from the actor registry", tip)
        self.assertIn("ckanext-actor-registry", plain)
        self.assertNotIn("choose a contact point from the actor registry", plain)

    def _licence_codes(self, dataset):
        return [f.code for f in review_dataset(dict({"title": "T"}, **dataset), make_profile()) if f.code == "hvd_licence"]

    def test_an_hvd_licence_must_be_cc0_or_cc_by(self):
        hvd = {"hvd_category": ["x"]}
        for good in ("cc-zero", "cc-by", "CC-BY-4.0", "https://creativecommons.org/licenses/by/4.0/",
                     "https://creativecommons.org/publicdomain/zero/1.0/",
                     "http://publications.europa.eu/resource/authority/licence/CC_BY_4_0"):
            self.assertEqual(self._licence_codes(dict(hvd, license_id=good)), [], good)
            self.assertEqual(self._licence_codes(dict(hvd, resources=[{"url": "u", "license": good}])), [], good)
        for bad in ("cc-nc", "CC-BY-SA-4.0", "https://creativecommons.org/licenses/by-nc/4.0/", "other-open"):
            self.assertEqual(self._licence_codes(dict(hvd, license_id=bad)), ["hvd_licence"], bad)
            self.assertEqual(self._licence_codes(dict(hvd, resources=[{"url": "u", "license": bad}])), ["hvd_licence"], bad)

    def test_the_licence_rule_is_silent_without_hvd_and_without_a_licence(self):
        self.assertEqual(self._licence_codes({"license_id": "cc-nc"}), [])
        self.assertEqual(self._licence_codes({"hvd_category": ["x"]}), [])

    def test_a_dataset_without_a_service_or_not_an_hvd_gets_no_remark(self):
        profile = make_profile(service_field="access_services")
        no_service = {"title": "T", "hvd_category": ["x"], "resources": [{"url": "https://example.org/a.csv"}]}
        not_hvd = {"title": "T", "resources": [{"url": "https://example.org/api", "access_services": [{"title": "API"}]}]}
        for dataset in (no_service, not_hvd):
            self.assertNotIn("hvd_service_without_contact", [f.code for f in review_dataset(dataset, profile)])

    def test_the_schema_decides_whether_the_rule_is_on(self):
        with_field = RuleProfile.from_scheming_dict("p", {"dataset_fields": [], "resource_fields": [{"field_name": "access_services"}]})
        without = RuleProfile.from_scheming_dict("p", {"dataset_fields": [], "resource_fields": [{"field_name": "url"}]})
        self.assertEqual((with_field.service_field, without.service_field), ("access_services", None))

    def test_a_distribution_field_has_a_label_and_a_dataset_field_keeps_its_own(self):
        profile = RuleProfile.from_scheming_dict("p", {
            "dataset_fields": [{"field_name": "notes", "label": "Beskrivning"}],
            "resource_fields": [{"field_name": "access_services", "label": "API (datatjänst)"},
                                {"field_name": "notes", "label": "Resursbeskrivning"}],
        })
        self.assertEqual(profile.label("access_services"), "API (datatjänst)")
        self.assertEqual(profile.label("notes"), "Beskrivning")


class SavedDatasetKeywordsTests(unittest.TestCase):
    """A saved dataset has tags, not the form's tag_string."""

    PROFILE = RuleProfile(name="t", recommended_fields=("tag_string",), keywords_field="tag_string")

    def test_tags_of_a_saved_dataset_count_as_keywords(self):
        dataset = {"title": "T", "tags": [{"name": "geodata"}, {"name": "karta"}]}
        codes = {f.code for f in review_dataset(dataset, self.PROFILE)}
        self.assertNotIn("recommended_field_missing", codes)

    def test_no_tags_and_no_tag_string_is_still_missing(self):
        codes = {f.code for f in review_dataset({"title": "T", "tags": []}, self.PROFILE)}
        self.assertIn("recommended_field_missing", codes)


class NewCompletenessRulesTests(unittest.TestCase):
    def codes(self, dataset, **profile):
        return [f.code for f in review_dataset(dataset, make_profile(**profile))]

    FULL = {"title": "Vägar", "owner_org": "o", "tag_string": "väg, gata", "theme": THEME_A, "license_id": "cc-by",
            "notes": " ".join(["ord"] * 30)}

    def test_a_short_but_not_tiny_description_gets_a_tip(self):
        data = dict(self.FULL, notes=" ".join(["ord"] * 12))
        self.assertIn("description_could_be_longer", self.codes(data, description_tip_words=25))
        finding = [f for f in review_dataset(data, make_profile(description_tip_words=25))
                   if f.code == "description_could_be_longer"][0]
        self.assertEqual(finding.severity, "info")
        self.assertNotIn("description_could_be_longer", self.codes(self.FULL, description_tip_words=25))
        self.assertNotIn("description_could_be_longer", self.codes(data, description_tip_words=10))

    def test_a_tiny_description_is_still_a_warning_and_not_also_a_tip(self):
        codes = self.codes(dict(self.FULL, notes="Tre korta ord"), description_tip_words=25)
        self.assertIn("description_too_short", codes)
        self.assertNotIn("description_could_be_longer", codes)

    def test_missing_licence_is_reported_when_the_schema_does_not_already_recommend_it(self):
        data = dict(self.FULL, license_id="")
        self.assertIn("license_missing", self.codes(data, license_field="license_id", recommended_fields=()))
        self.assertNotIn("license_missing", self.codes(data, license_field="license_id"))  # recommended: that rule speaks
        self.assertNotIn("license_missing", self.codes(self.FULL, license_field="license_id", recommended_fields=()))

    def test_one_keyword_or_very_many_gets_a_tip(self):
        self.assertIn("few_keywords", self.codes(dict(self.FULL, tag_string="väg")))
        self.assertIn("many_keywords", self.codes(dict(self.FULL, tag_string=", ".join("k%d" % i for i in range(16)))))
        self.assertNotIn("few_keywords", self.codes(self.FULL))


class TextQualityRulesTests(unittest.TestCase):
    def codes(self, dataset, **profile):
        return [f.code for f in review_dataset(dataset, make_profile(**profile))]

    def test_a_file_name_or_capitals_as_title_and_html_in_the_description(self):
        base = NewCompletenessRulesTests.FULL
        self.assertIn("title_looks_like_a_file_name", self.codes(dict(base, title="VÄGAR")))
        self.assertIn("title_looks_like_a_file_name", self.codes(dict(base, title="vagar_2020.csv")))
        self.assertNotIn("title_looks_like_a_file_name", self.codes(base))
        self.assertIn("description_contains_html", self.codes(dict(base, notes="<p>Text</p> " + base["notes"])))
        self.assertNotIn("description_contains_html", self.codes(dict(base, notes="a < b and b > c " + base["notes"])))

    def test_no_resources_only_when_the_dataset_lists_them(self):
        base = NewCompletenessRulesTests.FULL
        self.assertIn("no_resources", self.codes(dict(base, resources=[])))
        self.assertNotIn("no_resources", self.codes(base))                       # a form draft
        self.assertNotIn("no_resources", self.codes(dict(base, resources=[{"url": "x"}])))


# --- Addresses (2026-10-17) ---------------------------------------------------------------------------------------------------

def _address_codes(dataset):
    from ckanext.metadata_assistant.rules.links import check_links

    return [(f.code, f.severity) for f in check_links(dataset, _profile_for_links())]


def _profile_for_links():
    from ckanext.metadata_assistant.rules.profile import RuleProfile

    return RuleProfile.from_scheming_dict("p", {"dataset_fields": [], "resource_fields": []})


def test_an_address_with_a_space_or_without_a_scheme_is_a_warning():
    assert ("link_has_spaces", "warning") in _address_codes({"url": "https://example.org/a b"})
    assert ("link_without_scheme", "warning") in _address_codes({"url": "www.example.org/data"})
    assert ("link_without_scheme", "warning") in _address_codes({"url": "example.org"})
    assert _address_codes({"url": "mailto:someone@example.org", "documentation": ["urn:isbn:1"]}) == []


def test_plain_http_is_a_hint_except_for_specification_links():
    assert _address_codes({"url": "http://example.org/data"}) == [("link_not_secure", "info")]
    assert _address_codes({"conforms_to": ["http://www.opengis.net/spec/x"]}) == []
    assert _address_codes({"url": "https://example.org/data"}) == []


def test_lists_json_strings_resources_and_uploads_are_read():
    dataset = {"documentation": '["https://ok.example", "http://old.example/doc"]',
               "resources": [{"name": "Tabell", "url": "http://files.example/a.csv"},
                             {"name": "Uppladdad", "url": "a.csv", "url_type": "upload"}]}
    found = _address_codes(dataset)
    assert found == [("link_not_secure", "info"), ("link_not_secure", "info")]


def test_the_message_names_the_distribution_for_a_resource_address():
    from ckanext.metadata_assistant.rules.links import check_links

    [finding] = check_links({"resources": [{"name": "Tabell", "url": "http://files.example/a.csv"}]}, _profile_for_links())
    assert "'Tabell'" in finding.message and finding.field == ""


def test_an_unreadable_address_does_not_stop_the_review():
    assert _address_codes({"url": "https://[x"}) == []
