"""The setup check: what the assistant needs, and what is missing.

One list of checks for the metadata check settings page, the ``metadata_assistant_status`` action and the
``ckan metadata-assistant doctor`` command. Each check says whether it is fine and, when it is
not, what to do about it. Whether the AI connection can be used comes from ckanext-ai-connector (its own page lists its checks
and has a Test button). Nothing here calls the AI and no key is ever shown.
"""

from ckan import model as ckan_model
from ckan.plugins import toolkit

from ckanext.metadata_assistant.localization import _, language_name

OK, WARN, ERROR = "ok", "warning", "error"


def _check(key, status, title, detail="", fix=""):
    return {"key": key, "status": status, "title": title, "detail": detail, "fix": fix}


def _database():
    from ckanext.metadata_assistant.model import ReviewCache, TranslationProposal

    try:
        from sqlalchemy import inspect

        inspector = inspect(ckan_model.meta.engine)
        present = all(inspector.has_table(t.__tablename__) for t in (TranslationProposal, ReviewCache))
    except Exception as error:  # the database itself is not reachable
        return _check("database", ERROR, _("Database"), str(error)[:200])
    if present:
        return _check("database", OK, _("Database"), _("The assistant's tables exist."))
    return _check("database", ERROR, _("Database"), _("The assistant's tables are missing or out of date."),
                  "ckan -c $CKAN_INI db upgrade -p metadata_assistant")


def _ai():
    """The AI connection (ckanext-ai-connector): whether it can be used, and settings this extension saved for it before the
    move that still wait to be moved."""
    from ckanext.metadata_assistant import ai, migrate_ai

    checks = []
    leftover = migrate_ai.leftovers()
    if leftover:
        checks.append(_check("ai_migration", WARN, _("AI settings from before"),
                             _("Settings for the AI connection are still under this extension's old names ({names}) and are no longer used.").format(
                                 names=", ".join(leftover)),
                             "ckan -c $CKAN_INI metadata-assistant migrate-ai-settings"
                             + (" --remove-old" if _only_old_rows_left(leftover, migrate_ai) else "")))
    reason = ai.problem()
    if reason:
        return checks + [_check("ai_connector", WARN, _("AI"), reason + " " + _("Only the rule-based review works."))]
    described = ai.api.describe()
    return checks + [_check("ai_connector", OK, _("AI"), _("The shared AI connection is ready ({model}).").format(model=described["model"]))]


def _only_old_rows_left(leftover, migrate_ai):
    """True when the settings were moved and what waits is only old rows to delete (not server options or a key to
    encrypt again): then the fix is --remove-old."""
    try:
        if migrate_ai.moved() is None:
            return False
    except Exception:
        return False
    return all(name.startswith(migrate_ai.OLD) or name[len(migrate_ai.NEW):] in migrate_ai.RENAMED_NEW for name in leftover)


def _profile():
    from ckanext.metadata_assistant import profiles

    try:
        mode, detail = profiles.profile_source()
        profile = profiles.get_active_profile()
    except toolkit.ValidationError as error:
        message = next(iter(error.error_dict.values()))[0]
        return None, [_check("profile", ERROR, _("Metadata schema"), message)]
    except Exception as error:  # a schema file that cannot be read
        return None, [_check("profile", ERROR, _("Metadata schema"), str(error)[:200])]
    where = {
        "schema_file": _("the schema file %s") % detail,
        "scheming": _("the schema loaded by ckanext-scheming"),
        "ckan_core": _("CKAN's own fields (no schema)"),
    }[mode]
    checks = [_check("profile", OK, _("Metadata schema"),
                     "%s: %s" % (profile.name, where))]
    return profile, checks


LANDING_PAGE_FIELD = "url"


def _form_level(field_name):
    """The field's level and whether it is hidden, from ckanext-field-levels when its plugin is on; else None."""
    from ckan.plugins import plugin_loaded

    if not plugin_loaded("field_levels"):
        return None
    try:
        return toolkit.h.field_levels_field(field_name)
    except Exception:   # a level file that cannot be read is field-levels' own check
        return None


def _landing_page(profile):
    """The landing page is what the AI has most to go on: the field should be in the form, in sight, and asked for."""
    if profile is None:
        return []
    title = _("Landing page")
    if LANDING_PAGE_FIELD not in profile.field_labels:
        return [_check("landing_page", WARN, title,
                       _("The schema has no landing page field (url), so the AI has only the texts in the form to go on."),
                       _("Add the field url (dcat:landingPage) to the dataset schema."))]
    level = _form_level(LANDING_PAGE_FIELD)
    fix = _("Make the landing page recommended: url: recommended in the file named by ckanext.field_levels.file.")
    if level and level.get("hidden"):
        return [_check("landing_page", WARN, title,
                       _("The landing page field is hidden in the form, so editors cannot give the AI the page to read."), fix)]
    if level and level.get("level") == "optional":
        return [_check("landing_page", WARN, title,
                       _("The landing page field is optional, so the form folds it away and editors may not fill it in. "
                         "The AI suggestions are much better with the page."), fix)]
    if LANDING_PAGE_FIELD not in profile.recommended_fields and LANDING_PAGE_FIELD not in profile.required_fields:
        return [_check("landing_page", WARN, title,
                       _("The rule check does not ask for a landing page, though the AI suggestions are much better with "
                         "the page."),
                       _("Mark the field url with field_level: recommended in the dataset schema."))]
    return [_check("landing_page", OK, title,
                   _("The form asks for a landing page, which the AI reads for its suggestions."))]


def _languages(profile):
    if profile is None:
        return []
    if not profile.translation_targets or not profile.target_languages:
        return [_check("languages", WARN, _("Languages"),
                       _("The schema has no multilingual fields, so translation suggestions are off."),
                       _("Add multilingual fields (ckanext-fluent) to the schema to use them."))]
    targets = ", ".join(language_name(code) for code in profile.target_languages)
    return [_check("languages", OK, _("Languages"), "%s -> %s" % (
        language_name(profile.source_language), targets))]


def _guidance(profile):
    if profile is None:
        return []
    count = len(profile.field_guidance)
    if not count:
        return [_check("guidance", WARN, _("Guidelines for the AI"),
                       _("The AI has no guidelines for any field, so it judges by its own taste."),
                       _("Add help texts to the schema's fields."))]
    return [_check("guidance", OK, _("Guidelines for the AI"),
                   _("%d fields have guidelines (the schema's help texts, else the built-in baseline).") % count)]


def _background():
    from ckanext.metadata_assistant import cache, jobs, limits

    title = _("Background work")
    try:
        setting = jobs.mode()
        workers = jobs.workers_listening()
        redis = limits.connection()
        if redis is None:
            return [_check("background", WARN, title, _("Redis is not reachable, so AI requests run in the page."),
                           _("Check CKAN's Redis settings."))]
        from ckan.lib.jobs import get_queue

        waiting = len(get_queue(jobs.QUEUE))
        prepared = cache.prepared_count()
    except Exception as error:
        return [_check("background", WARN, title, str(error)[:200])]
    if setting == "off":
        return [_check("background", OK, title, _("Off: AI requests run in the page."))]
    if workers:
        detail = _("%d worker(s) listening, %d request(s) waiting, %d prepared review(s).") % (workers, waiting, prepared)
        hits = limits.hits_today(redis)
        if hits:
            names = {"rate_limited": _("the AI service limited us"), "breaker_opened": _("the AI service stopped answering"),
                     "busy": _("requests waited too long for a free place"), "user_quota": _("a person reached their limit")}
            what = ", ".join("%s: %d" % (names.get(k, k), n) for k, n in sorted(hits.items()))
            return [_check("background", WARN, title, detail + " " + _("Limits reached today (%s).") % what,
                           _("If this is common, use a stronger AI model or plan, or raise the limits."))]
        open_for = limits.breaker_open_for(redis)
        if open_for:
            return [_check("background", WARN, title, detail + " " + _("The AI service has failed repeatedly; requests wait %d seconds.") % open_for)]
        return [_check("background", OK, title, detail)]
    if setting == "on":
        return [_check("background", ERROR, title, _("Requests are queued but no worker is listening."),
                       "ckan -c $CKAN_INI metadata-assistant worker")]
    return [_check("background", OK, title, _("No worker: AI requests run in the page, which is fine for a few editors. When several work at once "
                     "(a training session, a large organisation) a request holds a web worker for seconds to minutes; "
                     "start a worker and requests are queued automatically, with no other change."),
                   "ckan -c $CKAN_INI metadata-assistant worker")]


def run_checks():
    """The checks, in the order a person sets things up."""
    profile, profile_checks = _profile()
    return ([_database()] + _ai() + profile_checks + _landing_page(profile) + _guidance(profile) + _languages(profile)
            + _background())
