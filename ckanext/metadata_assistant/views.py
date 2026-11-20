"""HTTP endpoint for the deterministic rule engine.

The dataset form's review button uses the matching CKAN action for
unsaved drafts. This endpoint remains useful for inspecting a saved dataset
directly as JSON.
"""

from __future__ import annotations

import ckan.plugins.toolkit as toolkit
from flask import Blueprint, jsonify
from ckanext.metadata_assistant.localization import _, language_name

blueprint = Blueprint("metadata_assistant", __name__)


@blueprint.route("/dataset/<dataset_id>/metadata-assistant/review")
def review(dataset_id):
    """Return rule-engine findings for one dataset, as JSON.

    Read-only (GET): runs no AI, saves nothing. Requires the same access a
    view of the dataset itself would.
    """
    context = {"user": toolkit.g.user, "auth_user_obj": toolkit.g.userobj}
    try:
        result = toolkit.get_action("metadata_assistant_review_dataset")(
            context, {"id": dataset_id}
        )
    except toolkit.ObjectNotFound:
        return jsonify({"success": False, "error": _("Dataset not found.")}), 404
    except toolkit.NotAuthorized:
        return jsonify({"success": False, "error": _("Not authorized.")}), 403
    return jsonify({"success": True, "result": result})


@blueprint.route("/metadata-assistant/help", strict_slashes=False)
def help():
    """How the assistant works, for editors: a page of text, no data."""
    return toolkit.render("metadata_assistant/help.html")


def _admin_context():
    user = toolkit.current_user
    return {"user": user.name if user.is_authenticated else ""}


@blueprint.route("/ckan-admin/metadata-assistant", methods=["GET", "POST"], strict_slashes=False)
def ai_settings():
    """The AI settings moved to ckanext-ai-connector (/ckan-admin/ai, 2026-11-18). An old link or bookmark goes there; without
    that extension's plugin, the check settings are where this extension's pages begin."""
    from ckanext.metadata_assistant import ai

    context = _admin_context()
    try:
        toolkit.check_access("metadata_assistant_ai_settings", context, {})
    except toolkit.NotAuthorized:
        return toolkit.abort(403, _("Not authorized."))
    from ckan.plugins import plugin_loaded

    if ai.api is not None and plugin_loaded("ai_connector"):
        return toolkit.redirect_to("ai_connector.settings_page")
    return toolkit.redirect_to("metadata_assistant.check_settings")


def ai_settings_url():
    """The AI settings page: ckanext-ai-connector's when its plugin is on (no detour through the old address), else the old
    address, which leads to this extension's check settings."""
    from ckan.plugins import plugin_loaded

    if plugin_loaded("ai_connector"):
        return toolkit.url_for("ai_connector.settings_page")
    return toolkit.url_for("metadata_assistant.ai_settings")


def _plugin_names():
    plugins = toolkit.config.get("ckan.plugins") or []
    return plugins.split() if isinstance(plugins, str) else list(plugins)


def _ai_ready():
    """Can the AI be used: ckanext-ai-connector is on, and a model and key are set? (The instructions to the AI do nothing
    without them.)"""
    from ckanext.metadata_assistant import ai

    return ai.ready()


@blueprint.route("/ckan-admin/metadata-assistant/check", methods=["GET", "POST"], strict_slashes=False)
def check_settings():
    """What the metadata check does, for sysadmins (2026-10-21): Markdown and the live address check.

    Separate from the AI page: the rule check works without any AI, and the address check needs the link check, not the AI.
    """
    from ckanext.metadata_assistant import admin_settings

    context = _admin_context()
    try:
        toolkit.check_access("metadata_assistant_ai_settings", context, {})
    except toolkit.NotAuthorized:
        return toolkit.abort(403, _("Not authorized."))

    form = {row["name"]: row["value"] for row in admin_settings.overview(admin_settings.CHECK_FIELDS)}
    errors = {}
    if toolkit.request.method == "POST":
        if toolkit.request.form.get("step") == "reset":
            admin_settings.reset(admin_settings.CHECK_FIELDS)
            toolkit.h.flash_success(_("The settings from the server's configuration apply again."))
            return toolkit.redirect_to("metadata_assistant.check_settings")
        submitted = {name: (toolkit.request.form.get(name) or "").strip() for name in admin_settings.CHECK_FIELDS}
        form.update(submitted)
        try:
            admin_settings.save(context, submitted)
        except toolkit.ValidationError as error:
            errors = error.error_dict
        else:
            toolkit.h.flash_success(_("The settings are saved and apply now."))
            return toolkit.redirect_to("metadata_assistant.check_settings")
    from ckanext.metadata_assistant import checks

    return toolkit.render("metadata_assistant/admin/check_settings.html", {
        "form": form, "errors": errors, "rows": admin_settings.overview(admin_settings.CHECK_FIELDS),
        "link_check_on": "link_check" in _plugin_names(), "checks": checks.run_checks()})


@blueprint.route("/ckan-admin/metadata-assistant/overview", strict_slashes=False)
def overview():
    """The gaps in the whole catalogue, by rule (sysadmins, 2026-10-29): which of the rule check's findings are common."""
    try:
        result = toolkit.get_action("metadata_assistant_catalogue_overview")(_admin_context(), {})
    except toolkit.NotAuthorized:
        return toolkit.abort(403, _("Not authorized."))
    return toolkit.render("metadata_assistant/admin/overview.html", {"overview": result})


def _dataset_id(text):
    """A dataset's name or id from what was typed: a name, or its address."""
    text = (text or "").strip().rstrip("/")
    if "/dataset/" in text:
        text = text.split("/dataset/", 1)[1].split("/", 1)[0].split("?", 1)[0]
    return text


@blueprint.route("/ckan-admin/metadata-assistant/instructions", methods=["GET", "POST"], strict_slashes=False)
def ai_instructions():
    """The catalogue's own instructions to the AI, for sysadmins (2026-10-03).

    The whole instruction to the AI is the text here, for a review and for a translation; ours is only the
    default. "Try on a dataset" runs it with the text in the form, without saving it.
    """
    from ckanext.metadata_assistant import admin_settings
    from ckanext.metadata_assistant.localization import language_name
    from ckanext.metadata_assistant.profiles import get_active_profile

    context = _admin_context()
    try:
        toolkit.check_access("metadata_assistant_ai_settings", context, {})
    except toolkit.NotAuthorized:
        return toolkit.abort(403, _("Not authorized."))

    form = {name: admin_settings.instructions(name) for name in admin_settings.INSTRUCTIONS}
    errors, trial, dataset_text = {}, None, ""
    if toolkit.request.method == "POST":
        step = toolkit.request.form.get("step")
        if step == "reset":
            admin_settings.reset(admin_settings.INSTRUCTIONS)
            toolkit.h.flash_success(_("The default instructions apply again."))
            return toolkit.redirect_to("metadata_assistant.ai_instructions")
        form = {name: toolkit.request.form.get(name) or "" for name in admin_settings.INSTRUCTIONS}
        trials = {"try": ("metadata_assistant_ai_review_dataset", "ai_review_instructions"),
                  "try_translation": ("metadata_assistant_translate_dataset",
                                      "ai_translation_instructions")}
        if step in trials:
            action, name = trials[step]
            dataset_text = toolkit.request.form.get("dataset") or ""
            try:
                result = toolkit.get_action(action)(context, {
                    "id": _dataset_id(dataset_text), "catalogue_instructions": form[name]})
                trial = {"kind": step, "result": result}
            except toolkit.ObjectNotFound:
                errors = {"dataset": [_("Dataset not found.")]}
            except toolkit.ValidationError as error:
                errors = {"dataset" if "id" in error.error_dict else name:
                          [str(v[0]) if isinstance(v, list) else str(v)
                           for v in error.error_dict.values()]}
        else:
            try:
                admin_settings.save_instructions(context, form)
            except toolkit.ValidationError as error:
                errors = error.error_dict
            else:
                toolkit.h.flash_success(_("The instructions are saved and apply now."))
                return toolkit.redirect_to("metadata_assistant.ai_instructions")

    try:
        profile = get_active_profile()
        per_language = [
            {"language": language_name(code),
             "instructions": (profile.translation_instructions or {}).get(code, ""),
             "terms": len((profile.translation_glossary or {}).get(code, {}))}
            for code in profile.target_languages]
    except Exception:
        per_language = []
    rows = {row["name"]: row for row in admin_settings.overview(admin_settings.INSTRUCTIONS)}
    return toolkit.render("metadata_assistant/admin/ai_instructions.html", {
        "form": form, "errors": errors, "trial": trial, "dataset": dataset_text,
        "defaults": {name: admin_settings.default_instructions(name)
                     for name in admin_settings.INSTRUCTIONS},
        "saved": {name: rows[name]["saved"] for name in rows},
        "per_language": per_language,
        "ai_ready": _ai_ready(),
        "max_length": admin_settings.INSTRUCTIONS_MAX_LENGTH,
    })


# --- Translation proposals (2026-10-06) -----------------------------------------------------------
# Proposals are made by `ckan metadata-assistant propose-translations` (see proposals.py). Here an
# editor reads each one next to the source text and applies it (edited or not) or rejects it.

TRANSLATIONS_PAGE_SIZE = 20


def _signed_in_user():
    user = toolkit.current_user
    if not user.is_authenticated:
        return toolkit.abort(403, _("Not authorized."))
    return user.name


@blueprint.route("/metadata-assistant/translations", strict_slashes=False)
def translations():
    """The open translation proposals the user may act on, newest first."""
    from ckan.lib.helpers import Page

    from ckanext.metadata_assistant import proposals

    user = _signed_in_user()
    page = toolkit.request.args.get("page", "1")
    page = int(page) if page.isdigit() and int(page) > 0 else 1
    rows, total = proposals.pending_for(user, page, TRANSLATIONS_PAGE_SIZE)
    cards = []
    for item in rows:
        try:
            dataset = toolkit.get_action("package_show")({"user": user}, {"id": item.package_id})
        except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
            continue
        suggestions = proposals.suggestions_of(item)
        for suggestion in suggestions:
            suggestion["edit_key"] = proposals.edit_key(suggestion)
            # The names of the languages in the page's language: a proposal made by the command was stored with the
            # command's (English) names.
            for code, label in (("language", "language_label"), ("source_language", "source_language_label")):
                if suggestion.get(code):
                    suggestion[label] = language_name(suggestion[code])
        cards.append({"item": item, "dataset": dataset, "suggestions": suggestions})
    pager = Page(collection=[], page=page, item_count=total, items_per_page=TRANSLATIONS_PAGE_SIZE,
                 url=lambda **kw: toolkit.url_for("metadata_assistant.translations", **kw))
    return toolkit.render("metadata_assistant/translations.html",
                          extra_vars={"cards": cards, "total": total, "pager": pager})


@blueprint.route("/metadata-assistant/translations/decide", methods=["POST"], strict_slashes=False)
def translations_decide():
    """Apply or reject proposals. Applying is explicit: one button per proposal, or the proposals
    the editor ticked after reading them. Edited text replaces the suggestion."""
    from ckanext.metadata_assistant import proposals

    user = _signed_in_user()
    form = toolkit.request.form
    if form.get("apply_one"):
        action, ids = "apply_one", [form["apply_one"]]
    elif form.get("reject_one"):
        action, ids = "reject_one", [form["reject_one"]]
    elif form.get("apply_ticked"):
        action, ids = "apply_ticked", form.getlist("ticked")
    else:
        action, ids = "", []
    applied = rejected = 0
    for proposal_id in ids:
        prefix = "edit__%s__" % proposal_id
        edits = {key[len(prefix):]: value for key, value in form.items() if key.startswith(prefix)}
        try:
            if action == "reject_one":
                proposals.reject(user, proposal_id)
                rejected += 1
            else:
                proposals.apply(user, proposal_id, edits)
                applied += 1
        except proposals.ProposalError as error:
            toolkit.h.flash_error(str(error))
    if applied:
        toolkit.h.flash_success(toolkit.ungettext("{count} translation applied.", "{count} translations applied.",
                                                  applied).format(count=applied))
    if rejected:
        toolkit.h.flash_success(toolkit.ungettext("{count} proposal rejected.", "{count} proposals rejected.",
                                                  rejected).format(count=rejected))
    if not ids:
        toolkit.h.flash_error(_("Choose at least one proposal."))
    page = form.get("page", "1")
    return toolkit.redirect_to("metadata_assistant.translations", page=page if page.isdigit() else 1)
