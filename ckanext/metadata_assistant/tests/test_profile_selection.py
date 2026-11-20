"""Which profile applies to a portal: a schema file, the Scheming schema, or CKAN's own fields."""

import pytest
from ckan.plugins import toolkit

from ckanext.metadata_assistant import profiles

P = profiles.PREFIX

SCHEMA_FILE = """\
scheming_version: 2
dataset_type: dataset
metadata_assistant:
  name: from_file
  recommended_fields: [tag_string]
dataset_fields:
- field_name: title
  label: Title
  required: true
- field_name: tag_string
  label: Tags
resource_fields: []
"""

pytestmark = [
    pytest.mark.ckan_config("ckan.plugins", "metadata_assistant ai_connector"),
    pytest.mark.usefixtures("with_plugins"),
]


@pytest.fixture
def schema_file(tmp_path):
    path = tmp_path / "schema.yaml"
    path.write_text(SCHEMA_FILE, encoding="utf-8")
    return str(path)


def test_a_portal_with_no_schema_gets_ckans_own_fields_without_any_setting():
    assert profiles.profile_source() == ("ckan_core", "")
    assert profiles.get_active_profile().name == "ckan_core"


def test_a_schema_file_is_used_when_one_is_named(schema_file, ckan_config, monkeypatch):
    monkeypatch.setitem(ckan_config, P + "schema_file", schema_file)
    assert profiles.profile_source() == ("schema_file", schema_file)
    profile = profiles.get_active_profile()
    assert profile.name == "from_file"
    assert profile.recommended_fields == ("tag_string",)


def test_the_profile_can_be_forced_to_ckans_own_fields(schema_file, ckan_config, monkeypatch):
    monkeypatch.setitem(ckan_config, P + "schema_file", schema_file)
    monkeypatch.setitem(ckan_config, P + "profile", "ckan_core")
    assert profiles.get_active_profile().name == "ckan_core"


def test_asking_for_a_schema_file_without_naming_one_says_what_to_do(ckan_config, monkeypatch):
    monkeypatch.setitem(ckan_config, P + "profile", "schema_file")
    with pytest.raises(toolkit.ValidationError) as error:
        profiles.get_active_profile()
    assert P + "schema_file" in error.value.error_dict


def test_asking_for_scheming_without_a_loaded_schema_says_what_to_do(ckan_config, monkeypatch):
    monkeypatch.setitem(ckan_config, P + "profile", "scheming")
    with pytest.raises(toolkit.ValidationError) as error:
        profiles.get_active_profile()
    assert P + "profile" in error.value.error_dict


def test_an_unknown_profile_is_refused(ckan_config, monkeypatch):
    monkeypatch.setitem(ckan_config, P + "profile", "nonsense")
    with pytest.raises(toolkit.ValidationError):
        profiles.profile_source()
