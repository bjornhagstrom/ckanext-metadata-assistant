"""Multilingual title, description and keywords with ckanext-fluent, for any catalogue.

ckanext-fluent stores a text as ``title_translated = {"sv": ..., "en": ...}`` and fills CKAN's own
``title`` only when a dataset is *read*. The database column and everything that reads it (lists,
actor registry, search) would stay empty. Two validators in the schema complete fluent_text:

    validators: metadata_assistant_fluent_from_core fluent_text metadata_assistant_fluent_to_core

- **from_core** (before fluent_text): a call that has ``title`` but no ``title_translated`` (an older API
  call, an import) gets the text as the default language's version.
- **to_core** (after fluent_text): writes the default language's text to the plain field and, when the
  field has ``fluent_required_language``, requires it. fluent's own ``required: true`` cannot be used: it
  demands every form language, and the others should be optional.

Keywords: ``metadata_assistant_fluent_tags_strip`` trims what fluent_tags leaves untrimmed, and
``metadata_assistant_fluent_tags_output`` survives an empty stored value (fluent's own crashes
package_show). The default language is ``ckan.locale_default``.

``metadata_assistant_scheming_missing_required_fields`` is an empty stand-in for a helper that
ckanext-fluent chains on and that only exists in ckanext-scheming's unreleased master; CKAN refuses to
start without it. It is registered only when scheming has no such helper of its own.
"""

from __future__ import annotations

import json

import ckan.plugins.toolkit as toolkit

SUFFIX = "_translated"


def default_language() -> str:
    return toolkit.config.get("ckan.locale_default") or "en"


def _core_key(key):
    name = key[-1]
    return key[:-1] + (name[: -len(SUFFIX)] if name.endswith(SUFFIX) else name,)


def _missing(value):
    return value is toolkit.missing or value is None or value == "" or value == {}


def _form_fields_present(key, data):
    prefix = key[-1] + "-"
    extras = data.get(key[:-1] + ("__extras",), {}) or {}
    return any(name.startswith(prefix) for name in extras)


def fluent_from_core(field, schema):
    def validator(key, data, errors, context):
        if not _missing(data.get(key, toolkit.missing)) or _form_fields_present(key, data):
            return
        core = data.get(_core_key(key), toolkit.missing)
        if not _missing(core):
            data[key] = json.dumps({default_language(): core}, ensure_ascii=False)
    return validator


def fluent_to_core(field, schema):
    required = field.get("fluent_required_language")

    def validator(key, data, errors, context):
        if errors.get(key):
            return
        value = data.get(key)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                value = {default_language(): value}
        value = value if isinstance(value, dict) else {}
        text = value.get(default_language()) or ""
        if required and not text:
            errors[key[:-1] + (key[-1] + "-" + required,)] = [toolkit._("Missing value")]
            errors[key].append(toolkit._("Text in the default language is missing."))
            return
        data[_core_key(key)] = text
    return validator


def strip_tags_by_language(tags):
    """{lang: [" a", "b "]} -> {lang: ["a", "b"]}, without empty ones."""
    return {lang: [t.strip() for t in words or [] if isinstance(t, str) and t.strip()]
            for lang, words in tags.items()}


def fluent_tags_strip(value):
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            parsed = json.loads(value)
        except ValueError:
            return value
        return json.dumps(strip_tags_by_language(parsed), ensure_ascii=False)
    if isinstance(value, dict):
        return strip_tags_by_language(value)
    return value


def fluent_tags_output(value):
    if isinstance(value, dict):
        return strip_tags_by_language(value)
    if value in (None, ""):
        return {}
    try:
        return strip_tags_by_language(json.loads(value))
    except (ValueError, AttributeError):
        return {}


def scheming_missing_required_fields(pages, data=None, package_id=None):
    return [[] for _ in pages]


def missing_fields_helper():
    """The stand-in, unless ckanext-scheming has the helper itself."""
    try:
        from ckanext.scheming import helpers
    except ImportError:
        return {}
    if hasattr(helpers, "scheming_missing_required_fields"):
        return {}
    return {"scheming_missing_required_fields": scheming_missing_required_fields}


def migrate(dry_run=False, echo=lambda text: None):
    """Give existing datasets their default-language text in the multilingual fields.

    Datasets made before the schema had ``title_translated`` have only ``title`` and ``notes``; the
    edit form would show empty boxes. The text is copied to ``*_translated = {default: text}``; no
    other language is invented. Touches only those fields, in the database, and reindexes the
    datasets it changed. Returns the number of datasets changed.
    """
    import ckan.model as model
    from ckan.lib.search import rebuild

    language = default_language()
    touched = set()
    for pkg in model.Session.query(model.Package).filter(model.Package.state != "deleted"):
        extras = pkg.extras
        for core, translated in (("title", "title_translated"), ("notes", "notes_translated")):
            current = getattr(pkg, core)
            if current and not extras.get(translated):
                echo("  dataset %s: %s" % (pkg.name, translated))
                if not dry_run:
                    extras[translated] = json.dumps({language: current}, ensure_ascii=False)
                touched.add(pkg.id)
    if not dry_run:
        model.Session.commit()
        for package_id in touched:
            rebuild(package_id)
    return len(touched)
