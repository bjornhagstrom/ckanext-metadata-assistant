"""CKAN actions exposed by the extension.

The deterministic action is locally verified. The semantic action remains
read-only and returns validated suggestions without saving them.
"""

from __future__ import annotations

import logging
import re

import ckan.plugins.toolkit as toolkit

from ckanext.metadata_assistant import markdown
from ckanext.metadata_assistant.guidance import BASELINE_GUIDANCE
from ckanext.metadata_assistant.profiles import get_active_profile
from ckanext.metadata_assistant.localization import _, language_name
from ckanext.metadata_assistant.rules import review_dataset as _review_dataset
from ckanext.metadata_assistant.link_results import findings_from_link_check, live_findings


def run_rules(dataset, profile, context=None):
    """The rule findings, and what the link check has found about the addresses (when it is installed)."""
    findings = list(_review_dataset(dataset, profile))
    if context is not None:
        findings.extend(findings_from_link_check(dataset, profile, context))
    return findings
from ckanext.metadata_assistant.llm import (
    LandingPageExtract,
    MetadataReviewRequest,
    ProviderError,
    ThemeChoice,
    TranslationRequest,
)

log = logging.getLogger(__name__)


def _provider():
    """The assistant's AI over the shared connection. A connection that cannot be used (no model, no key, or
    ckanext-ai-connector's plugin missing) is a ValidationError with the reason, as for a failed call, never an uncaught
    error."""
    from ckanext.metadata_assistant import ai

    try:
        return ai.assistant()
    except ProviderError as error:
        log.warning("Metadata assistant provider unavailable: %s", error)
        raise toolkit.ValidationError({"ai": [str(error)]}) from error


def _values(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(part.get("name") if isinstance(part, dict) else part).strip()
            for part in value
            if str(part.get("name") if isinstance(part, dict) else part).strip()]


def _keywords(dataset, profile):
    """The dataset's keywords, from the form's tag_string or a saved dataset's tags.

    package_show returns ``tags`` (a list of dicts), not ``tag_string``, so a
    review of a saved dataset used to see no keywords at all.
    """
    if not profile.keywords_field:
        return []
    return _values(dataset.get(profile.keywords_field)) or _values(dataset.get("tags"))


def _metadata_language(profile=None):
    """The language the metadata is written in: the profile's source
    language, else the site's main language. Not the dataset's own
    ``language`` field, which is the language of the data."""
    try:
        profile = profile or get_active_profile()
        if profile.translation_targets:
            return profile.source_language
    except Exception:
        pass
    return toolkit.config.get("ckan.locale_default") or "en"


def _landing_page_extract(data_dict):
    """Accept a previously read page from the caller, or nothing."""
    raw = data_dict.get("landing_page_extract")
    if not raw:
        return None
    try:
        return LandingPageExtract.model_validate(raw)
    except ValueError as error:
        raise toolkit.ValidationError(
            {"landing_page_extract": [_("Invalid page summary.")]}
        ) from error


def _authorized_dataset(context, data_dict, require_edit=False):
    """Return saved metadata or an authorized unsaved form draft.

    ``require_edit`` makes a saved dataset need edit rights, not just read
    rights. Used by the AI review: it spends money on the caller's behalf,
    so only editors and sysadmins may start it (the same bar as reading a
    landing page).
    """
    dataset = data_dict.get("dataset")
    if dataset is None:
        dataset_id = data_dict.get("id")
        if not dataset_id:
            raise toolkit.ValidationError({"id": ["Missing value"]})
        toolkit.check_access(
            "package_update" if require_edit else "package_show",
            context, {"id": dataset_id})
        return toolkit.get_action("package_show")(dict(context), {"id": dataset_id})

    dataset_id = dataset.get("id")
    if dataset_id:
        toolkit.check_access("package_update", context, {"id": dataset_id})
    else:
        toolkit.check_access("package_create", context, {})
    return _with_saved_translation_state(context, normalize_fluent_form(dataset))


def _with_saved_translation_state(context, dataset):
    """Give an unsaved form draft the saved dataset's translation digests.

    The digests live in a hidden field that the form never posts, but the
    ``translation_outdated`` rule needs them to compare against. Only for an
    existing dataset; a new one has none yet.
    """
    field = get_active_profile().translation_state_field
    if not field or dataset.get(field) or not dataset.get("id"):
        return dataset
    try:
        saved = toolkit.get_action("package_show")(dict(context), {"id": dataset["id"]})
    except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
        return dataset
    if saved.get(field):
        dataset = dict(dataset, **{field: saved[field]})
    return dataset


_FLUENT_FORM_KEY = re.compile(r"^(?P<base>.+)_translated-(?P<lang>[a-z]{2,8})$")


def normalize_fluent_form(dataset):
    """Give an unsaved ckanext-fluent form draft its plain field names.

    A fluent form posts e.g. ``title_translated-sv`` and
    ``title_translated-en`` instead of ``title``. The review works on the
    profile's source language (else ``ckan.locale_default``), falling back to the first
    language posted, and reads it as ``title``. Without this, a form using
    fluent is reviewed as if title and description were empty.
    """
    main = _metadata_language()
    found = {}
    for key, value in dataset.items():
        match = _FLUENT_FORM_KEY.match(str(key))
        if match:
            found.setdefault(match["base"], {})[match["lang"]] = value
    if not found:
        return dataset
    normalized = dict(dataset)
    for base, values in found.items():
        if normalized.get(base):
            continue
        normalized[base] = values.get(main) or next(iter(values.values()), "")
    return normalized


@toolkit.side_effect_free
def metadata_assistant_review_dataset(context, data_dict):
    """Run the deterministic rule engine against a dataset. Read-only.

    Never modifies the dataset, and never calls any AI service -- this action only runs the deterministic checks in
    ``ckanext.metadata_assistant.rules``. The AI-assisted review is the
    separate action ``metadata_assistant_ai_review_dataset``.

    Accepts either:

    - ``id``: an existing dataset's id or name. The dataset is re-fetched
      via ``package_show``, so the review reflects the last *saved* state.
    - ``dataset``: an already-built dataset dict, e.g. unsaved form data
      from the edit page. The form's review panel uses this to review a
      draft before it is saved.

    With ``check_addresses`` (a list of at most three addresses) and the sysadmin's setting for it, the link check is also asked, from the server,
    about those addresses (see link_results.live_findings); a failure there never fails the review.

    Requires the same access ``package_show`` would (read access to the
    dataset), enforced via ``check_access`` below.
    """
    dataset = _authorized_dataset(context, data_dict)

    profile = get_active_profile()
    findings = run_rules(dataset, profile, context)

    return {
        "profile": profile.name,
        "findings": [
            {
                "field": finding.field,
                # The editor sees the field's label, not its internal name.
                "label": profile.label(finding.field) if finding.field else "",
                "severity": finding.severity,
                "code": finding.code,
                "message": finding.message,
                "source": finding.source,
            }
            for finding in findings
        ] + [
            # What the link check says about the addresses the editor has just typed; `address` lets the page keep it
            # while the address stays in the form.
            {"field": "", "label": "", "severity": finding.severity, "code": finding.code, "message": finding.message,
             "source": finding.source, "address": address, "suggestion": finding.suggestion}
            for address, finding in live_findings(data_dict.get("check_addresses") or [], profile, context)
        ],
    }


@toolkit.side_effect_free
def metadata_assistant_read_landing_page(context, data_dict):
    """Read a public landing page once and return reusable facts. Read-only.

    Split out from the review action on purpose: the managed page fetch is
    the slow, failure-prone half of the work (40-90s, and the provider's
    capacity is not always there). Reading once per URL and reusing the
    result turns every later review into a fast, reliable call. Nothing is
    saved -- the caller holds the extract for the duration of the edit.
    """
    return execute_landing_page(prepare_landing_page(context, data_dict))


def prepare_landing_page(context, data_dict):
    """Check access and the address; return the job spec (plain data) for :func:`execute_landing_page`."""
    url = str(data_dict.get("url") or "").strip()
    if not url:
        raise toolkit.ValidationError({"url": ["Missing value"]})
    dataset_id = data_dict.get("id")
    if dataset_id:
        toolkit.check_access("package_update", context, {"id": dataset_id})
    else:
        toolkit.check_access("package_create", context, {})
    # Reuse the request contract's own validator: public HTTPS only, no
    # credentials in the URL, no loopback or private addresses.
    validated = MetadataReviewRequest(landing_page_url=url).landing_page_url
    if not validated:
        raise toolkit.ValidationError(
            {"url": [_("The landing page must be a public https address.")]}
        )
    return {"kind": "landing", "url": str(validated), "language": _metadata_language()}


AHEAD_AI_SECONDS = 30   # the longest the model may take to read a page that is read ahead of time


class _PortalFetchFailed(ProviderError):
    """The portal's own fetch of a landing page failed; ``service_may_help`` says whether to ask the AI service instead."""

    def __init__(self, message, service_may_help):
        super().__init__(message)
        self.service_may_help = service_may_help


def execute_landing_page(spec):
    """Read the page named by a spec from :func:`prepare_landing_page` (the slow part; no access checks)."""
    from ckanext.metadata_assistant import admin_settings, page_fetch

    provider = _provider()
    reader = getattr(provider, "read_landing_page", None)
    text_reader = getattr(provider, "read_landing_page_text", None)
    mode = admin_settings.landing_page_fetch_mode()   # auto (the portal's fetch, then the service's), own, or provider
    ahead = bool(spec.get("ahead"))
    if ahead and text_reader is not None:
        mode = "own"   # read ahead of time, which nobody asked for: no slow fallback to the service's fetch (up to 180 s of a web process)
    if reader is None and text_reader is None:
        raise toolkit.ValidationError({"ai": [_("The chosen AI provider cannot read landing pages.")]})

    def by_our_fetch():
        if text_reader is None:
            raise _PortalFetchFailed(_("The chosen AI provider cannot read landing pages."), True)
        try:
            text = page_fetch.fetch_text(spec["url"], spec.get("language"))
        except page_fetch.PageFetchError as error:
            # Not chained: a timeout here must not make the whole job run again.
            raise _PortalFetchFailed(str(error), error.service_may_help) from None
        if ahead:
            return text_reader(spec["url"], text, language=spec["language"], timeout=AHEAD_AI_SECONDS)
        return text_reader(spec["url"], text, language=spec["language"])

    try:
        if mode == "provider" or text_reader is None:
            extract = reader(spec["url"], language=spec["language"])
        elif mode == "own" or reader is None:
            extract = by_our_fetch()
        else:
            # The portal's own fetch is the quick one (about a second, against up to half a minute when the service's cannot reach the page);
            # the service's is for what needs a browser, a document, or a site that keeps the portal out. Not for a page that does not exist:
            # the service would only guess.
            try:
                extract = by_our_fetch()
            except _PortalFetchFailed as error:
                if not error.service_may_help:
                    raise
                log.info("Landing page: the portal's fetch failed (%s), asking the AI service", error)
                extract = reader(spec["url"], language=spec["language"])
    except ProviderError as error:
        log.warning("Landing page read failed: %s", error)
        raise toolkit.ValidationError({"ai": [str(error)]}) from error
    return extract.model_dump(mode="json")


@toolkit.side_effect_free
def metadata_assistant_ai_review_dataset(context, data_dict):
    """Return validated AI suggestions for selected metadata without saving.

    Only for those who may edit the dataset (or create one, for an unsaved
    draft): editors and sysadmins. Reading rights are not enough.
    """
    return execute_review(prepare_review(context, data_dict))


def prepare_review(context, data_dict):
    """Check access and build the review request; return the job spec (plain data) for :func:`execute_review`."""
    dataset = _authorized_dataset(context, data_dict, require_edit=True)
    profile = get_active_profile()
    owner_organisation = _owner_organisation(dataset)
    catalogue_name = str(toolkit.config.get("ckan.site_title") or "")
    request = MetadataReviewRequest(
        title=str(dataset.get(profile.title_field) or ""),
        description=str(dataset.get(profile.description_field) or ""),
        keywords=_keywords(dataset, profile),
        allowed_themes=[
            ThemeChoice(uri=uri, label=(getattr(profile, "theme_labels", None) or {}).get(
                uri, uri.rsplit("/", 1)[-1]))
            for uri in sorted(profile.theme_allowed_values)
        ],
        current_theme_uris=_values(dataset.get(profile.theme_field))
        if profile.theme_field
        else [],
        language=_metadata_language(profile),
        field_guidance=_guidance_for_request(profile, owner_organisation, catalogue_name),
        owner_organisation=owner_organisation,
        catalogue_name=catalogue_name,
        markdown=markdown.enabled(profile),
        landing_page_url=str(dataset.get("url") or "") or None,
        landing_page_extract=_landing_page_extract(data_dict),
        catalogue_instructions=_catalogue_instructions(
            context, data_dict, "ai_review_instructions"),
        rule_findings=_rule_findings_for_ai(dataset, profile),
    )
    return {"kind": "review", "package_id": dataset.get("id") or "",
            "request": request.model_dump(mode="json")}


def execute_review(spec):
    """Run the AI review for a spec from :func:`prepare_review` (the slow part; no access checks)."""
    profile = get_active_profile()
    request = MetadataReviewRequest.model_validate(spec["request"])
    provider = _provider()
    try:
        result = provider.review(request)
    except ProviderError as error:
        log.warning("Metadata assistant provider failed: %s", error)
        raise toolkit.ValidationError({"ai": [str(error)]}) from error
    return _without_unchanged_text(_clean_description_whitespace(_plain_when_markdown_is_off(
        _without_existing_keywords(result.model_dump(mode="json"), profile, request.keywords),
        profile, request.markdown), profile), profile, request)


def _without_unchanged_text(result, profile, request):
    """Drop a title or description suggestion that equals the current text (blank space aside): it changes nothing."""
    def same(a, b):
        return " ".join(str(a or "").split()) == " ".join(str(b or "").split())

    current = {profile.title_field: request.title, profile.description_field: request.description}
    kept = [s for s in result.get("suggestions") or []
            if not (s.get("field") in current and same(s.get("suggested_value"), current[s["field"]]))]
    return dict(result, suggestions=kept)


def _clean_description_whitespace(result, profile):
    """The description suggestion without blank space that changes nothing (see markdown.clean_whitespace)."""
    suggestions = []
    for suggestion in result.get("suggestions") or []:
        if suggestion.get("field") == profile.description_field and isinstance(suggestion.get("suggested_value"), str):
            suggestion = dict(suggestion, suggested_value=markdown.clean_whitespace(suggestion["suggested_value"]))
        suggestions.append(suggestion)
    return dict(result, suggestions=suggestions)


def _plain_when_markdown_is_off(result, profile, allowed):
    """The description suggestion as plain text when Markdown is off, whatever the model wrote."""
    if allowed:
        return result
    suggestions = []
    for suggestion in result.get("suggestions") or []:
        if suggestion.get("field") == profile.description_field and isinstance(suggestion.get("suggested_value"), str):
            suggestion = dict(suggestion, suggested_value=markdown.plain_text(suggestion["suggested_value"]))
        suggestions.append(suggestion)
    return dict(result, suggestions=suggestions)


def _guidance_for_request(profile, owner_organisation, catalogue_name):
    """The guidelines the AI gets, with the names a title and keywords must not repeat made concrete.

    "The organisation's name" is read by the model as any organisation's. The rule means the catalogue's own,
    so the guidance names it and says other names are not affected.
    """
    guidance = getattr(profile, "field_guidance", None) or {}
    names = [n for n in (owner_organisation, catalogue_name) if n]
    result = {}
    for name in (profile.title_field, profile.description_field, profile.keywords_field, profile.theme_field):
        if not name or not guidance.get(name):
            continue
        text = guidance[name]
        # Only the built-in baseline is made concrete; a schema's own help text is the catalogue's own rule.
        if names and name in (profile.title_field, profile.keywords_field) and text == BASELINE_GUIDANCE.get(name):
            text += (" The names not to repeat here are only the catalogue's own: %s. The name of any other "
                     "organisation, and a place the data is about, is not affected by this rule: if the "
                     "catalogue's own organisation is \"Acme\", the title \"Police incidents in Malmö\" is "
                     "correct as it is, with both \"Police\" and \"Malmö\" kept."
                     % "; ".join('"%s"' % n for n in names))
        result[name] = text
    return result


# The rule findings an AI suggestion can take care of, as codes (in no language, so that a review prepared by a
# worker and one asked for in a page share their cache entry).
_AI_RULE_CODES = ("description_too_short", "description_could_be_longer", "description_repeats_title",
                  "few_keywords", "many_keywords", "duplicate_keywords", "keywords_not_separated",
                  "theme_not_in_vocabulary", "recommended_field_missing", "required_field_missing")


def _rule_findings_for_ai(dataset, profile):
    fields = {profile.title_field, profile.description_field, profile.keywords_field, profile.theme_field}
    codes = []
    try:
        findings = run_rules(dataset, profile)
    except Exception:  # hints only: a failing rule must not stop the review
        log.warning("The completeness check failed; the review goes without its findings", exc_info=True)
        return []
    for finding in findings:
        if finding.code in _AI_RULE_CODES and finding.field in fields:
            item = "%s (%s)" % (finding.code, finding.field)
            if item not in codes:
                codes.append(item)
    return codes[:20]


def _owner_organisation(dataset):
    """The title of the organisation that owns the dataset in this catalogue ("" when unknown)."""
    organisation = dataset.get("organization")
    if isinstance(organisation, dict) and organisation.get("title"):
        return str(organisation["title"])
    owner = dataset.get("owner_org")
    if not owner:
        return ""
    from ckan import model

    group = model.Group.get(owner)
    return str(group.title or group.name) if group else ""


def _without_existing_keywords(result, profile, existing):
    """Drop suggested keywords the dataset already has (the AI sometimes repeats them).

    A keyword suggestion is added to the current keywords, so a repeated one changes nothing. A suggestion
    left with no new keyword is removed.
    """
    known = {str(k).strip().lower() for k in existing or []}
    kept = []
    for suggestion in result.get("suggestions") or []:
        if suggestion.get("field") == profile.keywords_field:
            value = suggestion.get("suggested_value")
            words = value if isinstance(value, list) else [w for w in str(value or "").split(",")]
            fresh = []
            for word in words:
                text = str(word).strip()
                if text and text.lower() not in known and text.lower() not in {f.lower() for f in fresh}:
                    fresh.append(text)
            if not fresh:
                continue
            suggestion = dict(suggestion, suggested_value=fresh if isinstance(value, list) else ", ".join(fresh))
        kept.append(suggestion)
    return dict(result, suggestions=kept)


@toolkit.side_effect_free
def metadata_assistant_translate_dataset(context, data_dict):
    """Suggest translations of the title, description and keywords.

    2026-09-27: English for metadata that goes to a national portal.
    2026-10-01: any source language and any number of target
    languages, all from the schema; ``languages`` picks some of them (default
    all). One AI request per language, so one that fails does not take the
    others with it. Returns suggestions only; nothing is saved, and an editor
    approves every one. Same access as the AI review: editors and sysadmins.

    Each suggestion names the source field (``title``, ``notes``,
    ``tag_string``), the field that holds its translations and the language,
    from the active profile -- the form finds the input from that (e.g.
    ``title_translated-en``).
    """
    return execute_translation(prepare_translation(context, data_dict))


def prepare_translation(context, data_dict):
    """Check access and build one request per language; return the job spec for :func:`execute_translation`."""
    dataset = _authorized_dataset(context, data_dict, require_edit=True)
    profile = get_active_profile()
    targets = dict(profile.translation_targets)
    if not targets or not profile.target_languages:
        raise toolkit.ValidationError(
            {"translation": [_("The profile has no fields for translation.")]})
    wanted = data_dict.get("languages") or list(profile.target_languages)
    languages = [lang for lang in profile.target_languages if lang in wanted]
    if not languages:
        raise toolkit.ValidationError(
            {"languages": [_("None of the requested languages is a target language.")]})

    title = str(dataset.get(profile.title_field) or "")
    description = str(dataset.get(profile.description_field) or "")
    keywords = _keywords(dataset, profile)
    source_name = language_name(profile.source_language)
    if not (title.strip() or description.strip() or keywords):
        raise toolkit.ValidationError({"translation": [
            _("There is no text in {language} to translate yet.").format(language=source_name)]})
    sources = {
        profile.title_field: title,
        profile.description_field: description,
        profile.keywords_field: keywords,
    }
    requests = []
    for language in languages:
        requests.append(TranslationRequest(
            source_language=profile.source_language,
            target_language=language,
            title=title, description=description, keywords=keywords,
            glossary=dict(profile.translation_glossary.get(language, {})),
            instructions=profile.translation_instructions.get(language, ""),
            catalogue_instructions=_catalogue_instructions(
                context, data_dict, "ai_translation_instructions"),
        ).model_dump(mode="json"))
    return {"kind": "translate", "package_id": dataset.get("id") or "",
            "requests": requests, "sources": sources}


def execute_translation(spec):
    """Run the translations for a spec from :func:`prepare_translation` (the slow part; no access checks)."""
    profile = get_active_profile()
    targets = dict(profile.translation_targets)
    source_name = language_name(profile.source_language)
    sources = spec["sources"]
    provider = _provider()
    translate = getattr(provider, "translate", None)
    if translate is None:
        raise toolkit.ValidationError(
            {"ai": [_("The chosen AI provider cannot translate.")]})
    suggestions, failed, first_cause = [], [], None
    for raw in spec["requests"]:
        request = TranslationRequest.model_validate(raw)
        language = request.target_language
        try:
            result = translate(request)
        except ProviderError as error:
            log.warning("Metadata translation failed: language=%s %s", language, error)
            failed.append({"language": language, "language_label": language_name(language),
                           "error": str(error)})
            first_cause = first_cause or error
            continue
        values = {
            profile.title_field: result.title,
            profile.description_field: result.description,
            profile.keywords_field: result.keywords,
        }
        for source, target in targets.items():
            value = values.get(source)
            if isinstance(value, str) and source == profile.description_field:
                value = markdown.clean_whitespace(value)
            if value:
                suggestions.append({
                    "field": source,
                    "target_field": target,
                    "language": language,
                    "language_label": language_name(language),
                    "source_language": profile.source_language,
                    "source_language_label": source_name,
                    "label": profile.label(source),
                    "suggested_value": value,
                    "source_value": sources.get(source),
                    "machine_translated": True,
                })
    if failed and not suggestions:
        raise toolkit.ValidationError({"ai": [failed[0]["error"]]}) from first_cause
    return {"suggestions": suggestions, "failed": failed}




def _catalogue_instructions(context, data_dict, name):
    """The catalogue's instructions for the AI. A sysadmin may pass a draft
    in ``catalogue_instructions`` to try it before saving (the admin page's
    "Try on a dataset"); for anyone else it is refused."""
    from ckanext.metadata_assistant import admin_settings

    draft = data_dict.get("catalogue_instructions")
    if draft is None:
        return admin_settings.instructions(name)
    toolkit.check_access("metadata_assistant_ai_settings", context, {})
    try:
        draft = admin_settings._instructions(draft)
    except toolkit.Invalid as error:
        raise toolkit.ValidationError({"catalogue_instructions": [error.error]})
    return draft


def metadata_assistant_ai_settings_reset(context, data_dict):
    """Forget the metadata check's settings saved in the interface (sysadmins). The AI connection's are ckanext-ai-connector's
    (ai_connector_reset)."""
    from ckanext.metadata_assistant import admin_settings

    toolkit.check_access("metadata_assistant_ai_settings", context, data_dict)
    admin_settings.reset()
    return {"reset": list(admin_settings.EDITABLE)}


def metadata_assistant_status(context, data_dict):
    """What the assistant needs and what is missing (sysadmins). Calls no AI service."""
    from ckanext.metadata_assistant import checks

    toolkit.check_access("metadata_assistant_ai_settings", context, data_dict)
    result = checks.run_checks()
    return {"ok": all(c["status"] != checks.ERROR for c in result), "checks": result}


@toolkit.side_effect_free
def metadata_assistant_catalogue_overview(context, data_dict):
    """How many datasets each rule of the check has something to say about, over the whole catalogue (sysadmins).

    Runs the deterministic rules only (no AI, no address checks), on every active dataset, and groups the findings by rule and field.

    :param limit: how many datasets to list per finding (default 50)
    :returns: ``{"datasets": n, "findings": [{"code", "field", "label", "severity", "message", "count", "datasets": [{"name", "title"}]}]}``,
        the most common first
    """
    toolkit.check_access("metadata_assistant_ai_settings", context, data_dict)
    limit = int(data_dict.get("limit") or 50)
    profile = get_active_profile()
    search_context = {"user": context.get("user") or "", "ignore_auth": True}
    groups, total, start = {}, 0, 0
    while True:
        page = toolkit.get_action("package_search")(dict(search_context), {
            "rows": 500, "start": start, "include_private": True})
        for dataset in page["results"]:
            total += 1
            counted = set()   # a dataset counts once per row, however many findings the rule has in it
            for finding in _review_dataset(dataset, profile):
                if (finding.code, finding.field or "") in counted:
                    continue
                counted.add((finding.code, finding.field or ""))
                group = groups.setdefault((finding.code, finding.field or ""), {
                    "code": finding.code, "field": finding.field or "",
                    "label": profile.label(finding.field) if finding.field else "",
                    "severity": finding.severity, "message": finding.message, "count": 0, "datasets": []})
                group["count"] += 1
                if len(group["datasets"]) < limit:
                    group["datasets"].append({"name": dataset["name"], "title": dataset.get("title") or dataset["name"]})
        start += 500
        if start >= page["count"]:
            break
    return {"datasets": total, "findings": sorted(groups.values(), key=lambda g: (-g["count"], g["code"], g["field"]))}


@toolkit.side_effect_free
def metadata_assistant_render_markdown(context, data_dict):
    """The text as the site renders Markdown, for the preview. Signed-in users only; nothing is stored."""
    if not context.get("user") and not context.get("ignore_auth"):
        raise toolkit.NotAuthorized("Sign in to preview.")
    return {"html": markdown.render(str(data_dict.get("text") or ""))}
