"""Translation proposals for existing datasets (2026-10-06).

``metadata_assistant_translate_dataset`` suggests translations for one dataset an editor has open.
This module does it in bulk for a catalogue: it finds the datasets whose translation is missing
(or out of date), asks the AI for suggestions, and *stores* them as proposals. A proposal changes
nothing. An editor reads it next to the source text and applies it, edited or not, or rejects it
(all metadata text is read and approved by a person; nothing is saved or published by
itself).

An applied proposal goes through ``package_patch`` as the editor, so the usual permissions and
validators apply, and the translation digest of the source text is updated as for any save. It is
refused (and marked stale) if the source text has changed since the proposal was made.
"""

from __future__ import annotations

import hashlib
import json
import logging

from ckan import model as ckan_model
from ckan.plugins import toolkit

from ckanext.metadata_assistant.localization import _
from ckanext.metadata_assistant.model import (
    APPLIED, PENDING, REJECTED, STALE, TranslationProposal, _now,
)
from ckanext.metadata_assistant.profiles import get_active_profile
from ckanext.metadata_assistant.rules.translations import (
    check_translations, language_value, source_digest, source_value,
)

log = logging.getLogger(__name__)

WANTED = ("translation_missing",)
WANTED_WITH_OUTDATED = ("translation_missing", "translation_outdated")


class ProposalError(Exception):
    """A proposal could not be applied; the message is shown to the editor."""


def source_texts(dataset, profile):
    """The source-language texts a translation is made from, keyed by source field."""
    return {field: source_value(dataset, field, profile.source_language)
            for field in profile.translation_targets}


def digest_of(dataset, profile):
    """One digest of all the source texts of a dataset."""
    texts = source_texts(dataset, profile)
    parts = json.dumps({field: source_digest(value) for field, value in sorted(texts.items())})
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


def needs_translation(dataset, profile, include_outdated=False):
    """Whether the review finds a translation missing (or, if asked, out of date)."""
    codes = WANTED_WITH_OUTDATED if include_outdated else WANTED
    return any(finding.code in codes for finding in check_translations(dataset, profile))


def latest(package_id):
    return (ckan_model.Session.query(TranslationProposal).filter_by(package_id=package_id)
            .order_by(TranslationProposal.created.desc()).first())


def candidates(context, profile, organization="", include_outdated=False, include_private=True):
    """Datasets with a translation to propose: no live proposal for the same source text, and
    nothing the editors have already decided on for it."""
    fq = ""
    if organization:
        org = toolkit.get_action("organization_show")(dict(context), {"id": organization})
        fq = "+owner_org:%s" % org["id"]
    start = 0
    while True:
        page = toolkit.get_action("package_search")(dict(context), {
            "fq": fq, "rows": 200, "start": start, "include_private": include_private,
            "sort": "name asc"})
        for dataset in page["results"]:
            if not needs_translation(dataset, profile, include_outdated):
                continue
            previous = latest(dataset["id"])
            if previous and previous.source_digest == digest_of(dataset, profile) and previous.status in (
                    PENDING, REJECTED, APPLIED):
                continue
            yield dataset
        start += 200
        if start >= page["count"]:
            return


def _translate(context, dataset_id):
    """The AI call. A separate function so tests can replace it."""
    return toolkit.get_action("metadata_assistant_translate_dataset")(dict(context), {"id": dataset_id})


def propose(context, dataset, profile=None):
    """Ask the AI for suggestions for ``dataset`` and store them. Returns the new proposal, or
    ``None`` if there was nothing to suggest. Raises ``ValidationError`` when the AI call fails."""
    profile = profile or get_active_profile()
    result = _translate(context, dataset["id"])
    # A suggestion identical to its source (text that is already in the target language) is no proposal.
    suggestions = [s for s in (result.get("suggestions") or []) if not _same(s.get("source_value"), s.get("suggested_value"))]
    if not suggestions:
        return None
    for old in ckan_model.Session.query(TranslationProposal).filter_by(
            package_id=dataset["id"], status=PENDING):
        old.status = STALE
    item = TranslationProposal(package_id=dataset["id"], status=PENDING,
                               source_digest=digest_of(dataset, profile),
                               suggestions=json.dumps(suggestions, ensure_ascii=False))
    ckan_model.Session.add(item)
    ckan_model.Session.commit()
    return item


def _same(source, suggestion):
    """Whether a suggested text says nothing new: equal to the source, ignoring case and spacing."""
    def norm(value):
        parts = value if isinstance(value, (list, tuple)) else [value]
        return sorted(" ".join(str(part or "").lower().split()) for part in parts)
    return norm(source) == norm(suggestion)


def suggestions_of(item):
    return json.loads(item.suggestions or "[]")


def edit_key(suggestion):
    """The name of the form field an editor changes a suggestion in."""
    return "%s__%s" % (suggestion["target_field"], suggestion["language"])


def _unique(values):
    seen, out = set(), []
    for value in values:
        key = str(value).strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(str(value).strip())
    return out


def _as_list(value):
    if isinstance(value, (list, tuple)):
        return [str(part).strip() for part in value if str(part).strip()]
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def build_patch(dataset, suggestions, edits=None):
    """The ``package_patch`` data for applying ``suggestions`` (a list as stored), with the
    editor's text in ``edits`` (keyed by :func:`edit_key`) in place of a suggestion's own."""
    edits = edits or {}
    patch = {}
    for suggestion in suggestions:
        target, language = suggestion["target_field"], suggestion["language"]
        text = edits.get(edit_key(suggestion))
        value = suggestion["suggested_value"] if text is None else text
        current = dict(patch.get(target) or (dataset.get(target) if isinstance(dataset.get(target), dict) else {}) or {})
        if isinstance(suggestion["suggested_value"], (list, tuple)):
            existing = _as_list(language_value(dataset, target, language))
            current[language] = _unique(existing + _as_list(value))
        else:
            current[language] = str(value).strip()
        patch[target] = current
    return patch


def apply(user, proposal_id, edits=None):
    """Apply a proposal as ``user``. Raises ``ProposalError`` with a message for the editor."""
    item = ckan_model.Session.get(TranslationProposal, proposal_id)
    if item is None or item.status != PENDING:
        raise ProposalError(_("This proposal is no longer open."))
    context = {"user": user}
    try:
        toolkit.check_access("package_update", dict(context), {"id": item.package_id})
        dataset = toolkit.get_action("package_show")(dict(context), {"id": item.package_id})
    except (toolkit.NotAuthorized, toolkit.ObjectNotFound):
        raise ProposalError(_("You may not edit this dataset."))
    profile = get_active_profile()
    if digest_of(dataset, profile) != item.source_digest:
        item.status = STALE
        ckan_model.Session.commit()
        raise ProposalError(_("The text of the dataset has changed since this was proposed. "
                              "Ask for a new proposal."))
    patch = build_patch(dataset, suggestions_of(item), edits)
    try:
        toolkit.get_action("package_patch")(dict(context), dict(patch, id=item.package_id))
    except toolkit.ValidationError as error:
        ckan_model.Session.rollback()
        raise ProposalError(_("The dataset could not be saved: {message}").format(
            message="; ".join("%s: %s" % (key, ", ".join(map(str, value)))
                              for key, value in error.error_dict.items())))
    item = ckan_model.Session.get(TranslationProposal, proposal_id)
    item.status, item.decided, item.decided_by = APPLIED, _now(), user
    ckan_model.Session.commit()
    return item


def reject(user, proposal_id):
    item = ckan_model.Session.get(TranslationProposal, proposal_id)
    if item is None or item.status != PENDING:
        raise ProposalError(_("This proposal is no longer open."))
    try:
        toolkit.check_access("package_update", {"user": user}, {"id": item.package_id})
    except (toolkit.NotAuthorized, toolkit.ObjectNotFound):
        raise ProposalError(_("You may not edit this dataset."))
    item.status, item.decided, item.decided_by = REJECTED, _now(), user
    ckan_model.Session.commit()
    return item


def pending_for(user, page=1, per_page=20):
    """The open proposals ``user`` may act on, newest first: ``(rows, total)``. A sysadmin sees all;
    others the datasets of the organizations where they are editor or admin."""
    query = ckan_model.Session.query(TranslationProposal).filter_by(status=PENDING)
    if not _is_sysadmin(user):
        org_ids = [org["id"] for org in toolkit.get_action("organization_list_for_user")(
            {"user": user}, {"permission": "update_dataset"})]
        if not org_ids:
            return [], 0
        ids = [pid for (pid,) in ckan_model.Session.query(ckan_model.Package.id).filter(
            ckan_model.Package.owner_org.in_(org_ids))]
        query = query.filter(TranslationProposal.package_id.in_(ids))
    total = query.count()
    rows = (query.order_by(TranslationProposal.created.desc())
            .offset((page - 1) * per_page).limit(per_page).all())
    return rows, total


def _is_sysadmin(user):
    from ckan.authz import is_sysadmin
    return bool(user) and is_sysadmin(user)
