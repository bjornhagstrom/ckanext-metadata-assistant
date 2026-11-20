"""Move this extension's old AI connection settings to ckanext-ai-connector (``ckan metadata-assistant migrate-ai-settings``).

Up to 0.1.x the connection (model, key, time limits) was this extension's, under ``ckanext.metadata_assistant.ai_*``, with
keys entered on the page stored under ``ckanext.metadata_assistant.secret.<NAME>``. It is ckanext-ai-connector's now, under its
own names, and ckanext-ai-connector reads nothing of this extension's. This module is the one place that knows both: it copies
the values saved in the interface, re-encrypts the stored keys under ckanext-ai-connector's cipher and copies the list of added
keys. It prints and logs names only, never a value or a key.

It writes through ckanext-ai-connector's internal ``keys`` and ``settings`` modules (the public ``api`` has no place for a
migration); it goes when the old names do.

Options in the server's configuration (.env, the ini file) cannot be moved by a command: :data:`SERVER_RENAMES` lists them for
whoever runs the server, and :func:`leftovers` names those still set.
"""

from __future__ import annotations

import base64
import hashlib
import json

from ckan import model
from ckan.plugins import toolkit

OLD = "ckanext.metadata_assistant."
NEW = "ckanext.ai_connector."
# The values saved in the interface: old name -> new name (None: no longer an option).
SAVED = {"ai_model": "model", "ai_api_key_env": "api_key_env", "ai_timeout_seconds": "timeout_seconds",
         "ai_url_context_timeout_seconds": "page_read_timeout_seconds", "ai_provider": None}
# Names an unreleased development version of ckanext-ai-connector (then called ckanext-ai-config) used for a while. Its rows
# are found here once they are renamed to the new prefix (one UPDATE of system_info.key, done by hand where it ran).
RENAMED_NEW = {"url_context_timeout_seconds": "page_read_timeout_seconds", "provider": None}
OLD_CUSTOM_KEYS = OLD + "ai_custom_key_names"
NEW_CUSTOM_KEYS = NEW + "custom_key_names"
OLD_SECRET = OLD + "secret."
NEW_SECRET = NEW + "secret."
# Written after the first move (this extension's row, kept by --remove-old): a later run copies nothing again.
MOVED = OLD + "ai_settings_moved"
# The server's options, for the .env file: old -> new (CKAN reads CKANEXT__A__B as ckanext.a.b).
SERVER_RENAMES = {
    "ai_model": "model",
    "ai_api_key_env": "api_key_env",
    "ai_api_key_envs": "api_key_envs",
    "ai_api_base": "api_base",
    "ai_timeout_seconds": "timeout_seconds",
    "ai_url_context_timeout_seconds": "page_read_timeout_seconds",
    "ai_provider": None,
}


def env_name(option):
    return "CKANEXT__" + option.replace("ckanext.", "", 1).replace(".", "__").upper()


def _old_fernet():
    """The cipher this extension used for stored keys (and ckanext-ai-connector's development version, before ``v1:``)."""
    secret = toolkit.config.get("SECRET_KEY") or toolkit.config.get("beaker.session.secret")
    if not secret:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None
    derived = hashlib.sha256(b"ckanext-metadata-assistant api key\0" + str(secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def _rows(prefix):
    column = model.SystemInfo.key
    return dict(model.Session.query(column, model.SystemInfo.value).filter(
        column.like(prefix.replace("_", r"\_") + "%", escape="\\")).all())


def moved():
    """When the settings were moved (the time as text), or None: a later run copies nothing again, so that a key removed or
    a value reset on the AI settings page never comes back."""
    return model.get_system_info(MOVED)


def _server_option(key):
    """An old option from the server's configuration, read without CKAN's warning about an option nobody declares (the old
    names are no longer declared: they are only looked for here)."""
    try:
        return str(toolkit.config[key] if key in toolkit.config else "").strip()
    except Exception:
        return ""


def leftovers():
    """The names of old settings that still wait: values saved in the interface under the old names, keys stored under the
    old cipher, and the server's options under the old names. Names only. Never raises."""
    try:
        found = []
        old_rows, new_rows = _rows(OLD), _rows(NEW)
        for old in list(SAVED) + ["ai_custom_key_names"]:
            if old_rows.get(OLD + old) not in (None, ""):
                found.append(OLD + old)
        for key, value in old_rows.items():
            if key.startswith(OLD_SECRET):
                found.append(key)
        for key, value in new_rows.items():
            if key.startswith(NEW_SECRET) and value and not value.startswith("v1:"):
                found.append(key)
            if key[len(NEW):] in RENAMED_NEW:
                found.append(key)
        for old, new in SERVER_RENAMES.items():
            if _server_option(OLD + old) and not (new and (toolkit.config.get(NEW + new) or "").strip()):
                found.append(env_name(OLD + old))
        return found
    except Exception:
        return []


def _old_row_names(old_rows, new_rows):
    """The rows --remove-old deletes: the old saved values, list of added keys and stored keys, and the names an earlier
    development version of ckanext-ai-connector used."""
    names = [OLD + old for old in list(SAVED) + ["ai_custom_key_names"] if (OLD + old) in old_rows]
    names += sorted(key for key in old_rows if key.startswith(OLD_SECRET))
    names += sorted(key for key in new_rows if key[len(NEW):] in RENAMED_NEW)
    return names


def migrate(dry_run=False, echo=print):
    """Copy the old saved values, keys and list of added keys to ckanext-ai-connector's names, once: where nothing is saved under
    the new name yet, and only when the settings have not been moved before (:func:`moved`). Keys stored by ckanext-ai-connector's
    development version without the ``v1:`` prefix are encrypted again in place, also later. Returns the names written.
    Raises RuntimeError when a stored key cannot be read (the portal's secret changed): then nothing is written."""
    from ckanext.ai_connector import keys as ai_keys, settings as ai_settings

    old_rows, new_rows = _rows(OLD), _rows(NEW)
    first = moved() is None
    writes = []   # (key, value), written only when everything could be read

    if first:
        # The values saved in the interface (and the names of the development version).
        for old, new in SAVED.items():
            value = old_rows.get(OLD + old)
            if value not in (None, "") and new and new_rows.get(NEW + new) in (None, ""):
                writes.append((NEW + new, value))
        for old, new in RENAMED_NEW.items():
            value = new_rows.get(NEW + old)
            if value is not None and new and new_rows.get(NEW + new) in (None, "") \
                    and NEW + new not in {key for key, _ in writes}:
                writes.append((NEW + new, value))

        # The list of added keys.
        names = []
        for raw in (old_rows.get(OLD_CUSTOM_KEYS), new_rows.get(NEW_CUSTOM_KEYS)):
            try:
                names += [n for n in json.loads(raw or "[]") if isinstance(n, str) and n not in names]
            except ValueError:
                pass
        if names and json.dumps(names) != new_rows.get(NEW_CUSTOM_KEYS):
            writes.append((NEW_CUSTOM_KEYS, json.dumps(names)))

    # The keys: decrypt with the old cipher, encrypt with ckanext-ai-connector's. A key of the development version (under the
    # new name, without "v1:") is always encrypted again: it is the current key, so nothing removed comes back.
    tokens = {}
    if first:
        tokens.update({key[len(OLD_SECRET):]: token for key, token in old_rows.items()
                       if key.startswith(OLD_SECRET) and not (new_rows.get(NEW_SECRET + key[len(OLD_SECRET):]) or "").startswith("v1:")})
    tokens.update({key[len(NEW_SECRET):]: token for key, token in new_rows.items()
                   if key.startswith(NEW_SECRET) and token and not token.startswith("v1:")})
    fernet = _old_fernet() if tokens else None
    for name, token in sorted(tokens.items()):
        if fernet is None:
            raise RuntimeError("The stored key %s cannot be read: the portal has no secret or cryptography is missing." % name)
        try:
            plain = fernet.decrypt(token.encode()).decode()
        except Exception:
            raise RuntimeError("The stored key %s cannot be read with the portal's secret. Enter it again on the AI settings page." % name) from None
        writes.append((NEW_SECRET + name, ai_keys.encrypt(plain)))

    if not dry_run:
        for key, value in writes:
            model.set_system_info(key, value)
        if first:
            import datetime

            model.set_system_info(MOVED, datetime.datetime.utcnow().isoformat(timespec="seconds"))
        if writes:
            import time

            from ckan.lib import app_globals

            model.set_system_info("ckan.config_update", str(time.time()))
            app_globals.reset()
        ai_settings.forget_rows()
    if not first and not writes:
        echo("The settings were moved on %s; nothing is copied again." % moved())
    for key, _value in writes:
        echo(("would copy " if dry_run else "copied ") + key)
    return [key for key, _value in writes]


def remove_old(dry_run=False, echo=print):
    """Delete the old rows (see :func:`_old_row_names`), only after the settings were moved. Copies nothing. Returns the names
    removed. Raises RuntimeError when the settings have not been moved yet."""
    from ckanext.ai_connector import settings as ai_settings

    if moved() is None:
        raise RuntimeError("The settings have not been moved yet. Run the command without --remove-old first.")
    names = _old_row_names(_rows(OLD), _rows(NEW))
    if not dry_run:
        for key in names:
            model.delete_system_info(key)
        ai_settings.forget_rows()
    for key in names:
        echo(("would remove " if dry_run else "removed ") + key)
    return names
