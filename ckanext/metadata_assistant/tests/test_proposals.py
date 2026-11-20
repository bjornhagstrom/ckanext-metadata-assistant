"""Translation proposals for existing datasets: storage, rules for what is proposed, applying
and rejecting, who sees what. The AI call and the dataset actions are replaced by fakes; nothing
here calls a provider."""

import json
from types import SimpleNamespace

import pytest
from ckan import model as ckan_model
from ckan.plugins import toolkit
from ckan.tests import factories

from ckanext.metadata_assistant import proposals
from ckanext.metadata_assistant.model import APPLIED, PENDING, REJECTED, STALE, TranslationProposal
from ckanext.metadata_assistant.profiles import build_profile
from ckanext.metadata_assistant.tests.test_translation import SCHEMA

PROFILE = build_profile(SCHEMA, name="dcat_ap_se")

SUGGESTIONS = [
    {"field": "title", "target_field": "title_translated", "language": "en", "language_label": "English",
     "source_language": "sv", "source_language_label": "Swedish", "label": "Title", "suggested_value": "Bathing sites",
     "source_value": "Badplatser", "machine_translated": True},
    {"field": "tag_string", "target_field": "keywords_translated", "language": "en", "language_label": "English",
     "source_language": "sv", "source_language_label": "Swedish", "label": "Keywords", "suggested_value": ["bathing site", "water"],
     "source_value": ["badplats", "vatten"], "machine_translated": True},
]


def _dataset(title="Badplatser", english="", keywords=("badplats", "vatten"), **extra):
    data = {"id": "d-1", "name": "badplatser", "title": title,
            "title_translated": {"sv": title, **({"en": english} if english else {})},
            "notes": "Text.", "notes_translated": {"sv": "Text."},
            "tags": [{"name": k} for k in keywords], "keywords_translated": {"sv": list(keywords)}}
    data.update(extra)
    return data


# --- Pure functions ------------------------------------------------------------------------------

def test_the_digest_follows_the_source_text_and_not_the_translation():
    base = proposals.digest_of(_dataset(), PROFILE)
    assert proposals.digest_of(_dataset(english="Bathing sites"), PROFILE) == base
    assert proposals.digest_of(_dataset(title="Badplatser 2025"), PROFILE) != base
    assert proposals.digest_of(_dataset(keywords=("badplats",)), PROFILE) != base


def test_a_missing_translation_is_proposed_and_an_existing_one_is_not():
    assert proposals.needs_translation(_dataset(), PROFILE)
    complete = _dataset(english="Bathing sites", notes_translated={"sv": "Text.", "en": "Text."},
                        keywords_translated={"sv": ["badplats", "vatten"], "en": ["bathing site"]})
    assert not proposals.needs_translation(complete, PROFILE)


def test_applying_adds_the_language_and_keeps_the_others():
    patch = proposals.build_patch(_dataset(), SUGGESTIONS)
    assert patch["title_translated"] == {"sv": "Badplatser", "en": "Bathing sites"}
    assert patch["keywords_translated"] == {"sv": ["badplats", "vatten"], "en": ["bathing site", "water"]}


def test_keywords_are_added_to_the_existing_ones_without_repeats():
    dataset = _dataset(keywords_translated={"sv": ["badplats"], "en": ["Water", "lake"]})
    patch = proposals.build_patch(dataset, SUGGESTIONS)
    assert patch["keywords_translated"]["en"] == ["Water", "lake", "bathing site"]


def test_the_editors_text_replaces_the_suggestion():
    key = proposals.edit_key(SUGGESTIONS[0])
    patch = proposals.build_patch(_dataset(), SUGGESTIONS, {key: " Bathing places "})
    assert patch["title_translated"]["en"] == "Bathing places"


# --- With a database -----------------------------------------------------------------------------

integration = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "metadata_assistant ai_connector"),
    pytest.mark.usefixtures("with_plugins", "metadata_assistant_db"),
]


def _mark(test):
    for mark in reversed(integration):
        test = mark(test)
    return test


@pytest.fixture
def metadata_assistant_db(clean_db, migrate_db_for):
    migrate_db_for("metadata_assistant")


@pytest.fixture(autouse=True)
def fake_profile(monkeypatch):
    monkeypatch.setattr(proposals, "get_active_profile", lambda: PROFILE)


class FakeCkan:
    """Replaces ``toolkit.get_action`` and ``check_access`` inside proposals.py."""

    def __init__(self, monkeypatch, dataset=None, allowed=True):
        self.dataset, self.patches, self.translated = dataset or _dataset(), [], 0
        self.allowed = allowed

        def get_action(name):
            def call(context, data):
                if name == "package_show":
                    return self.dataset
                if name == "package_patch":
                    self.patches.append(data)
                    return data
                if name == "package_search":
                    return {"results": [self.dataset], "count": 1}
                raise AssertionError(name)
            return call

        def check_access(name, context, data):
            if not self.allowed:
                raise toolkit.NotAuthorized()

        monkeypatch.setattr(proposals.toolkit, "get_action", get_action)
        monkeypatch.setattr(proposals.toolkit, "check_access", check_access)
        monkeypatch.setattr(proposals, "_translate", self._translate)

    def _translate(self, context, dataset_id):
        self.translated += 1
        return {"suggestions": [dict(s) for s in SUGGESTIONS], "failed": []}


def _all():
    return ckan_model.Session.query(TranslationProposal).order_by(TranslationProposal.created).all()


@_mark
def test_a_proposal_is_stored_and_a_new_one_replaces_the_open_one(monkeypatch):
    fake = FakeCkan(monkeypatch)
    first = proposals.propose({"user": "site"}, fake.dataset, PROFILE)
    second = proposals.propose({"user": "site"}, fake.dataset, PROFILE)
    assert first.status == STALE and second.status == PENDING
    assert [item.status for item in _all()] == [STALE, PENDING]
    assert json.loads(second.suggestions)[0]["suggested_value"] == "Bathing sites"
    assert fake.patches == []


@_mark
def test_a_suggestion_equal_to_its_source_is_dropped(monkeypatch):
    fake = FakeCkan(monkeypatch)
    same = [dict(SUGGESTIONS[0], source_value="Badplatser", suggested_value=" badplatser "),
            dict(SUGGESTIONS[1], source_value=["Bad", "vatten"], suggested_value=["vatten", "bad"])]
    monkeypatch.setattr(proposals, "_translate", lambda context, dataset_id: {"suggestions": same})
    assert proposals.propose({"user": "site"}, fake.dataset, PROFILE) is None
    assert _all() == []
    mixed = same + [dict(SUGGESTIONS[0], language="de", suggested_value="Badestellen")]
    monkeypatch.setattr(proposals, "_translate", lambda context, dataset_id: {"suggestions": mixed})
    item = proposals.propose({"user": "site"}, fake.dataset, PROFILE)
    assert [s["language"] for s in json.loads(item.suggestions)] == ["de"]


@_mark
def test_nothing_is_stored_when_the_ai_has_nothing_to_suggest(monkeypatch):
    fake = FakeCkan(monkeypatch)
    monkeypatch.setattr(proposals, "_translate", lambda context, dataset_id: {"suggestions": []})
    assert proposals.propose({"user": "site"}, fake.dataset, PROFILE) is None
    assert _all() == []


@_mark
def test_a_dataset_with_a_proposal_or_a_decision_for_the_same_text_is_not_asked_again(monkeypatch):
    fake = FakeCkan(monkeypatch)
    assert [d["id"] for d in proposals.candidates({"user": "site"}, PROFILE)] == ["d-1"]
    item = proposals.propose({"user": "site"}, fake.dataset, PROFILE)
    assert list(proposals.candidates({"user": "site"}, PROFILE)) == []
    proposals.reject("site", item.id)
    assert list(proposals.candidates({"user": "site"}, PROFILE)) == []
    # The source text changes: it is a candidate again.
    fake.dataset = _dataset(title="Badplatser 2025")
    assert [d["id"] for d in proposals.candidates({"user": "site"}, PROFILE)] == ["d-1"]


@_mark
def test_applying_saves_through_the_dataset_actions_as_the_editor(monkeypatch):
    fake = FakeCkan(monkeypatch)
    item = proposals.propose({"user": "site"}, fake.dataset, PROFILE)
    proposals.apply("editor", item.id, {proposals.edit_key(SUGGESTIONS[0]): "Bathing places"})
    [patch] = fake.patches
    assert patch["id"] == "d-1" and patch["title_translated"]["en"] == "Bathing places"
    assert patch["keywords_translated"]["en"] == ["bathing site", "water"]
    done = _all()[0]
    assert (done.status, done.decided_by) == (APPLIED, "editor")
    with pytest.raises(proposals.ProposalError):
        proposals.apply("editor", item.id)


@_mark
def test_a_proposal_for_changed_source_text_is_refused_and_marked_stale(monkeypatch):
    fake = FakeCkan(monkeypatch)
    item = proposals.propose({"user": "site"}, fake.dataset, PROFILE)
    fake.dataset = _dataset(title="Badplatser 2025")
    with pytest.raises(proposals.ProposalError, match="changed"):
        proposals.apply("editor", item.id)
    assert fake.patches == [] and _all()[0].status == STALE


@_mark
def test_someone_who_may_not_edit_the_dataset_cannot_apply_or_reject(monkeypatch):
    fake = FakeCkan(monkeypatch)
    item = proposals.propose({"user": "site"}, fake.dataset, PROFILE)
    fake.allowed = False
    for action in (proposals.apply, proposals.reject):
        with pytest.raises(proposals.ProposalError, match="may not edit"):
            action("outsider", item.id)
    assert fake.patches == [] and _all()[0].status == PENDING


@_mark
def test_a_rejected_proposal_changes_nothing(monkeypatch):
    fake = FakeCkan(monkeypatch)
    item = proposals.propose({"user": "site"}, fake.dataset, PROFILE)
    proposals.reject("editor", item.id)
    assert _all()[0].status == REJECTED and fake.patches == []


def _stored(package_id):
    item = TranslationProposal(package_id=package_id, status=PENDING, source_digest="x",
                               suggestions=json.dumps(SUGGESTIONS))
    ckan_model.Session.add(item)
    ckan_model.Session.commit()
    return item


@_mark
def test_who_sees_which_proposals():
    editor, outsider, sysadmin = factories.User(), factories.User(), factories.Sysadmin()
    org = factories.Organization(users=[{"name": editor["name"], "capacity": "editor"}])
    other = factories.Organization()
    mine = factories.Dataset(owner_org=org["id"])
    theirs = factories.Dataset(owner_org=other["id"])
    _stored(mine["id"]), _stored(theirs["id"])
    assert [item.package_id for item in proposals.pending_for(editor["name"])[0]] == [mine["id"]]
    assert proposals.pending_for(outsider["name"]) == ([], 0)
    assert proposals.pending_for(sysadmin["name"])[1] == 2


@_mark
def test_the_page_lists_the_open_proposals_of_the_editor_and_needs_a_login(app):
    editor = factories.UserWithToken()
    org = factories.Organization(users=[{"name": editor["name"], "capacity": "editor"}])
    dataset = factories.Dataset(owner_org=org["id"], title="Bathing sites")
    _stored(dataset["id"])
    app.get("/metadata-assistant/translations", status=403)
    html = app.get("/metadata-assistant/translations", headers={"Authorization": editor["token"]}).get_data(as_text=True)
    assert "Bathing sites" in html and "Machine-translated: check before applying" in html
    assert 'name="edit__' in html and "Badplatser" in html and html.count("data-proposal=") == 1
    # The language names follow the page, not the language the proposal was stored in (the command stores English).
    html = app.get("/sv/metadata-assistant/translations",
                   headers={"Authorization": editor["token"]}).get_data(as_text=True)
    assert "Title, engelska" in html and "Title, svenska" in html
    assert ", English<" not in html and ", Swedish<" not in html


@_mark
def test_deciding_through_the_page_uses_the_edited_text_and_only_the_ticked(app, monkeypatch):
    editor = factories.UserWithToken()
    calls = []
    monkeypatch.setattr(proposals, "apply", lambda user, pid, edits=None: calls.append((user, pid, edits)))
    monkeypatch.setattr(proposals, "reject", lambda user, pid: calls.append(("reject", user, pid)))
    key = proposals.edit_key(SUGGESTIONS[0])
    headers = {"Authorization": editor["token"]}
    app.post("/metadata-assistant/translations/decide", headers=headers,
             data={"apply_one": "p1", "edit__p1__" + key: "Bathing places", "edit__p2__" + key: "ignored"})
    app.post("/metadata-assistant/translations/decide", headers=headers,
             data={"apply_ticked": "1", "ticked": ["p2", "p3"]})
    app.post("/metadata-assistant/translations/decide", headers=headers, data={"reject_one": "p4"})
    assert calls == [(editor["name"], "p1", {key: "Bathing places"}), (editor["name"], "p2", {}),
                     (editor["name"], "p3", {}), ("reject", editor["name"], "p4")]
    app.post("/metadata-assistant/translations/decide", status=403, data={"apply_one": "p1"})
