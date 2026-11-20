"""The overview of the whole catalogue: how common each finding of the rule check is (2026-10-29)."""

import pytest
from ckan.plugins import toolkit
from ckan.tests import factories, helpers

pytestmark = [
    pytest.mark.ckan_config("ckan.plugins", "metadata_assistant ai_connector"),
    pytest.mark.usefixtures("with_plugins", "clean_db", "clean_index"),
]


def _call(user, **data):
    return helpers.call_action("metadata_assistant_catalogue_overview",
                               context={"user": user["name"], "ignore_auth": False}, **data)


def test_findings_are_counted_per_rule_over_all_datasets_including_private_ones():
    org = factories.Organization()
    factories.Dataset(title="Utan licens", owner_org=org["id"], license_id="")
    factories.Dataset(title="Privat utan licens", owner_org=org["id"], private=True, license_id="")
    factories.Dataset(title="Med licens", owner_org=org["id"], license_id="cc-by")
    result = _call(factories.Sysadmin())
    assert result["datasets"] == 3
    license_missing = [f for f in result["findings"] if f["field"] == "license_id"]
    assert [f["count"] for f in license_missing] == [2]
    assert {d["title"] for d in license_missing[0]["datasets"]} == {"Utan licens", "Privat utan licens"}
    assert [f["count"] for f in result["findings"] if f["code"] == "no_resources"] == [3]   # run on the dataset, resources and all
    counts = [f["count"] for f in result["findings"]]
    assert counts == sorted(counts, reverse=True)
    assert len(_call(factories.Sysadmin(), limit=1)["findings"][0]["datasets"]) == 1


def test_only_a_sysadmin_may_see_it_and_the_page_shows_the_shares(app):
    with pytest.raises(toolkit.NotAuthorized):
        _call(factories.User())
    factories.Dataset(license_id="")
    sysadmin = factories.SysadminWithToken()
    page = app.get("/ckan-admin/metadata-assistant/overview", headers={"Authorization": sysadmin["token"]}).body
    assert "Catalogue overview" in page and "100" in page
    user = factories.UserWithToken()
    app.get("/ckan-admin/metadata-assistant/overview", headers={"Authorization": user["token"]}, status=403)
