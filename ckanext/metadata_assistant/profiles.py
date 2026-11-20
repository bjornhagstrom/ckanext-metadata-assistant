"""Wires the framework-agnostic rule engine to CKAN, ckanext-scheming and config.

This is the only module in the extension allowed to import ``yaml`` or
``ckan.plugins.toolkit`` -- everything under ``ckanext.metadata_assistant.rules``
stays free of those dependencies on purpose. The part that needs no CKAN
instance (:func:`build_profile`) can be unit tested; see test_profiles.py.

Which profile applies (``ckanext.metadata_assistant.profile``, default ``auto``):

``auto``       a schema file if ``ckanext.metadata_assistant.schema_file`` is set, else the
               dataset schema ckanext-scheming has loaded, else the built-in ``ckan_core``.
``schema_file`` the schema file; the option must be set.
``scheming``   the dataset schema ckanext-scheming has loaded.
``ckan_core``  CKAN's own fields (title, description, tags, licence, ...), for a portal
               without a schema.

A catalogue declares what is particular to it in an optional top-level
``metadata_assistant`` block of its schema (see :func:`build_profile`); nothing about any
one catalogue is built into this extension.
"""

from __future__ import annotations

import dataclasses
import functools
from typing import Mapping, Optional

from ckanext.metadata_assistant.guidance import baseline_for
from ckanext.metadata_assistant.localization import _
from ckanext.metadata_assistant.rules import RuleProfile

PREFIX = "ckanext.metadata_assistant."
MODES = ("auto", "schema_file", "scheming", "ckan_core")

# Recommended when a schema says nothing: the fields most portals have. Only those the schema
# actually has are used.
DEFAULT_RECOMMENDED_FIELDS = ("tag_string", "license_id", "url")

def ckan_core_schema():
    """CKAN's own dataset fields, for a portal with no schema at all (labels in the page's language)."""
    return {
        "dataset_fields": [
            {"field_name": "title", "label": _("Title"), "required": True},
            {"field_name": "notes", "label": _("Description")},
            {"field_name": "tag_string", "label": _("Tags")},
            {"field_name": "license_id", "label": _("License")},
            {"field_name": "url", "label": _("Source")},
            {"field_name": "maintainer", "label": _("Maintainer")},
            {"field_name": "maintainer_email", "label": _("Maintainer email")},
        ],
        "resource_fields": [],
        "metadata_assistant": {
            "name": "ckan_core",
            "recommended_fields": ["tag_string", "license_id", "url"],
        },
    }


def build_profile(
    schema: Mapping[str, object],
    *,
    name: str = "schema",
    source_language: Optional[str] = None,
) -> RuleProfile:
    """Build a :class:`RuleProfile` from an already-parsed ckanext-scheming schema dict.

    Pure function: no file or CKAN access. Everything is read from the schema, and the
    schema may refine it in a top-level ``metadata_assistant`` block (all keys optional):

    ``name``                  the profile's name (shown in findings).
    ``recommended_fields``    fields that should have a value. Else the fields marked
                              ``field_level: recommended``, else a small default.
    ``theme_field``, ``keywords_field``, ``license_field``, ``title_field``,
    ``description_field``, ``min_description_words``  as in :class:`RuleProfile`.
    ``guidance_markers``      strings that end a help text's instruction (the rest is a note
                              for the editor, not for the AI).
    ``translation_source``    where the translation requirement comes from, shown in findings.
    ``markdown``              true or false to say whether descriptions are Markdown; else it follows the description
                              field's form snippet (``markdown.html``, ``fluent_markdown.html``).
    ``description_tip_words``  a description shorter than this gets a tip that it could be longer (default 25).
    ``translation_level``     ``optional`` (default), ``recommended`` or ``required``: how strongly a missing
                              translation is reported for multilingual (ckanext-fluent) fields.
    ``baseline_guidance``     false to leave out the built-in guidance (guidance.py) for fields whose help
                              text says nothing. Default true.

    Translations come from the schema field that holds ``translation_targets`` (see
    ``rules.profile``), or else from the multilingual fields themselves.
    """
    settings = dict(schema.get("metadata_assistant") or {})
    dataset_fields = [f for f in schema.get("dataset_fields", []) if "field_name" in f]
    present = {f["field_name"] for f in dataset_fields}

    def setting(key, default):
        return settings.get(key) if settings.get(key) is not None else default

    recommended = settings.get("recommended_fields")
    if recommended is None:
        recommended = [
            f["field_name"] for f in dataset_fields
            if f.get("field_level") == "recommended" and not f["field_name"].endswith("_translated")
        ] or [f for f in DEFAULT_RECOMMENDED_FIELDS if f in present]

    theme_field = setting("theme_field", "theme" if "theme" in present else None)
    keywords_field = setting("keywords_field", "tag_string" if "tag_string" in present else None)
    license_field = setting("license_field", "license_id" if "license_id" in present else None)

    profile = RuleProfile.from_scheming_dict(
        str(setting("name", name)),
        schema,
        recommended_fields=tuple(recommended),
        theme_field=theme_field,
        keywords_field=keywords_field,
        title_field=setting("title_field", "title"),
        description_field=setting("description_field", "notes"),
        license_field=license_field,
        min_description_words=int(setting("min_description_words", 8)),
        description_tip_words=int(setting("description_tip_words", 25)),
        translation_level=str(setting("translation_level", "optional")),
        guidance_markers=tuple(settings.get("guidance_markers") or ()),
        translation_source=str(settings.get("translation_source") or ""),
        source_language=source_language,
    )
    if settings.get("markdown") is not None:
        description_markdown = bool(settings["markdown"])
    else:
        description_markdown = any(
            "markdown" in str(f.get("form_snippet") or "")
            for f in dataset_fields
            if (f["field_name"][: -len("_translated")] if f["field_name"].endswith("_translated") else f["field_name"])
            == profile.description_field)
    profile = dataclasses.replace(profile, description_markdown=description_markdown)
    if settings.get("baseline_guidance", True):
        present_core = {n[: -len("_translated")] if n.endswith("_translated") else n for n in present}
        wanted = present_core | ({"theme"} if theme_field else set())
        baseline = baseline_for(wanted)
        if baseline:
            profile = dataclasses.replace(profile, field_guidance={**baseline, **profile.field_guidance})
    return profile


def load_profile_from_file(path: str) -> RuleProfile:
    """Read a scheming schema YAML file from disk and build a profile from it."""
    import yaml

    with open(path, "r", encoding="utf-8") as fh:
        schema = yaml.safe_load(fh)
    return build_profile(schema, name="schema_file", source_language=_source_language())


@functools.lru_cache(maxsize=8)
def _cached_profile_for_file(path: str) -> RuleProfile:
    return load_profile_from_file(path)


def _source_language() -> Optional[str]:
    """The portal's default language, the language its texts are written in."""
    import ckan.plugins.toolkit as toolkit

    return toolkit.config.get("ckan.locale_default") or None


def _scheming_schema():
    """The dataset schema ckanext-scheming has loaded, or None without scheming."""
    try:
        from ckanext.scheming.helpers import scheming_get_dataset_schema
    except ImportError:
        return None
    try:
        return scheming_get_dataset_schema("dataset")
    except Exception:  # scheming loaded but no dataset schema configured
        return None


def profile_source():
    """Which profile applies and where it comes from: ``(mode, detail)``.

    ``mode`` is ``"schema_file"``, ``"scheming"`` or ``"ckan_core"``; ``detail`` the file path
    for a file, else ``""``. Raises ``ValidationError`` when the configuration asks for
    something that is not there.
    """
    import ckan.plugins.toolkit as toolkit

    asked = (toolkit.config.get(PREFIX + "profile") or "auto").strip()
    if asked not in MODES:
        raise toolkit.ValidationError({PREFIX + "profile": [
            _("Unknown profile '%s'. Use one of: %s.") % (asked, ", ".join(MODES))]})
    path = toolkit.config.get(PREFIX + "schema_file") or ""
    if asked == "ckan_core":
        return "ckan_core", ""
    if asked in ("auto", "schema_file") and path:
        return "schema_file", path
    if asked == "schema_file":
        raise toolkit.ValidationError({PREFIX + "schema_file": [
            _("Config option not set. Point it at the ckanext-scheming schema YAML file this "
              "portal uses, or leave the profile on 'auto'.")]})
    if asked in ("auto", "scheming") and _scheming_schema():
        return "scheming", ""
    if asked == "scheming":
        raise toolkit.ValidationError({PREFIX + "profile": [
            _("ckanext-scheming has no dataset schema loaded. Use the profile 'ckan_core' "
              "or point schema_file at a schema.")]})
    return "ckan_core", ""


def get_active_profile() -> RuleProfile:
    """Return the :class:`RuleProfile` to use for this CKAN instance (see the module docstring)."""
    mode, detail = profile_source()
    if mode == "schema_file":
        return _cached_profile_for_file(detail)
    if mode == "scheming":
        return build_profile(_scheming_schema(), name="scheming", source_language=_source_language())
    return build_profile(ckan_core_schema(), name="ckan_core")
