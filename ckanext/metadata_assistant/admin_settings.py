"""Settings a sysadmin may change in the interface: what the metadata check does and the instructions to the AI.

The connection to the AI (model, key, time limits) is ckanext-ai-connector's, which every extension that uses AI shares; its
page is /ckan-admin/ai. Settings this extension saved for the connection before (``ckanext.metadata_assistant.ai_*``) are
moved there by ``ckan metadata-assistant migrate-ai-settings`` (see migrate_ai.py).

The check settings and the instructions are runtime-editable CKAN options (update_config_schema): stored by CKAN's
config_option_update in the database, applied at once in every worker, and falling back to the server's configuration (.env)
when nothing is stored.
"""

import time

from ckan import model
from ckan.plugins import toolkit

from ckanext.metadata_assistant.localization import _

PREFIX = "ckanext.metadata_assistant."
# The metadata-check page saves what the checks do.
CHECK_FIELDS = ("markdown", "check_addresses", "landing_page_fetch", "read_page_on_open")
EDITABLE = CHECK_FIELDS
# The catalogue's own instructions to the AI (2026-10-03), added to the
# locked core of each prompt (llm/prompts.py). Until something is saved the
# default text applies; a saved empty text means no instructions of our own.
INSTRUCTIONS = ("ai_review_instructions", "ai_translation_instructions")
INSTRUCTIONS_MAX_LENGTH = 12000

def server_default(name):
    """The value from the server's configuration (.env or the ini file),
    whatever the interface has saved. CKAN keeps it aside the first time it
    applies saved values (ckan.lib.app_globals._CONFIG_CACHE)."""
    from ckan.lib import app_globals

    key = PREFIX + name
    if key in app_globals._CONFIG_CACHE:
        return app_globals._CONFIG_CACHE[key] or ""
    return toolkit.config.get(key) or ""


def stored(name):
    """The value saved in the interface, or None."""
    return model.get_system_info(PREFIX + name)


# --- validators for update_config_schema -----------------------------------









def _markdown(value):
    value = (value or "auto").strip().lower()
    if value not in ("auto", "on", "off"):
        raise toolkit.Invalid(_("Choose auto, on or off."))
    return value


def _on_off(value):
    value = (value or "off").strip().lower()
    if value not in ("on", "off"):
        raise toolkit.Invalid(_("Choose on or off."))
    return value


LANDING_PAGE_FETCH_MODES = ("auto", "own", "provider")


def _landing_page_fetch(value):
    value = (value or "auto").strip().lower()
    if value not in LANDING_PAGE_FETCH_MODES:
        raise toolkit.Invalid(_("Choose auto, own or provider."))
    return value


def landing_page_fetch_mode():
    """How a landing page is read: ``auto`` (the portal's own fetch, then the AI service's if that fails), ``own`` (always the portal's)
    or ``provider`` (only the service's)."""
    value = str(toolkit.config.get(PREFIX + "landing_page_fetch") or "auto").strip().lower()
    return value if value in LANDING_PAGE_FETCH_MODES else "auto"


def _on_off_default_on(value):
    value = (value or "on").strip().lower()
    if value not in ("on", "off"):
        raise toolkit.Invalid(_("Choose on or off."))
    return value


def _instructions(value):
    value = (value or "").replace("\r\n", "\n").strip()
    if len(value) > INSTRUCTIONS_MAX_LENGTH:
        raise toolkit.Invalid(_("Keep the instructions under {count} characters.").format(
            count=INSTRUCTIONS_MAX_LENGTH))
    return value


def default_instructions(name):
    """The text used when nothing is saved: the server's, else the code's."""
    from ckanext.metadata_assistant.llm import prompts

    code = {"ai_review_instructions": prompts.DEFAULT_REVIEW_INSTRUCTIONS,
            "ai_translation_instructions": prompts.DEFAULT_TRANSLATION_INSTRUCTIONS}[name]
    return (server_default(name) or code).strip()


def instructions(name):
    """The catalogue's instructions in use for the review or translation.
    A saved text, even an empty one, goes before the default."""
    saved = stored(name)
    return saved.strip() if saved is not None else default_instructions(name)


def save_instructions(context, submitted):
    """Save the texts that differ from the default, an emptied one too (no
    instructions of our own); a text set back to the default is no longer
    overridden."""
    changed, back = {}, []
    for name, value in submitted.items():
        value = (value or "").replace("\r\n", "\n").strip()
        if value == default_instructions(name):
            if stored(name) is not None:
                back.append(name)
        else:
            changed[PREFIX + name] = value
    try:
        if changed:
            toolkit.get_action("config_option_update")(context, changed)
    except toolkit.ValidationError as error:
        raise toolkit.ValidationError({key.replace(PREFIX, ""): value
                                       for key, value in error.error_dict.items()})
    if back:
        reset(back)


def update_config_schema(schema):
    ignore_missing = toolkit.get_validator("ignore_missing")
    unicode_safe = toolkit.get_validator("unicode_safe")
    schema.update({
        PREFIX + "markdown": [ignore_missing, unicode_safe, _markdown],
        PREFIX + "check_addresses": [ignore_missing, unicode_safe, _on_off],
        PREFIX + "landing_page_fetch": [ignore_missing, unicode_safe, _landing_page_fetch],
        PREFIX + "read_page_on_open": [ignore_missing, unicode_safe, _on_off_default_on],
        PREFIX + "ai_review_instructions": [ignore_missing, unicode_safe, _instructions],
        PREFIX + "ai_translation_instructions": [ignore_missing, unicode_safe, _instructions],
    })
    return schema


def same_as_server(name, value):
    """True when a submitted value is what the server's configuration says."""
    default = server_default(name)
    if name == "markdown":
        return (str(value).strip() or "auto") == (str(default).strip() or "auto")
    if name == "check_addresses":
        return (str(value).strip() or "off") == (str(default).strip() or "off")
    if name == "read_page_on_open":
        return (str(value).strip() or "on") == (str(default).strip() or "on")
    if name == "landing_page_fetch":
        return (str(value).strip() or "auto") == (str(default).strip() or "auto")
    return str(value).strip() == str(default).strip()


def save(context, submitted):
    """Save the values that differ from the server's configuration; a value
    set back to the server's is no longer overridden. Raises
    ValidationError with the setting names (without prefix) as keys."""
    own = dict(submitted)
    changed = {PREFIX + name: value for name, value in own.items()
               if not same_as_server(name, value)}
    try:
        if changed:
            toolkit.get_action("config_option_update")(context, changed)
    except toolkit.ValidationError as error:
        raise toolkit.ValidationError({key.replace(PREFIX, ""): value
                                       for key, value in error.error_dict.items()})
    back = [name for name in own
            if PREFIX + name not in changed and stored(name) is not None]
    if back:
        reset(back)


def overview(names=EDITABLE):
    """What the admin page shows: per setting the value in use, the server's
    value and whether the interface has overridden it."""
    rows = []
    for name in names:
        saved = stored(name)
        rows.append({"name": name, "value": toolkit.config.get(PREFIX + name) or "",
                     "default": server_default(name), "saved": saved is not None})
    return rows


def reset(names=EDITABLE):
    """Forget the values saved in the interface; the server's apply again."""
    from ckan.lib import app_globals

    for name in names:
        model.delete_system_info(PREFIX + name)
    model.set_system_info("ckan.config_update", str(time.time()))
    app_globals.reset()
