"""Translations: are they missing, and are they in step with the source text?

2026-09-27: English for metadata that goes to a national portal, and every
translation is approved by an editor. 2026-10-01: language-neutral, with the
languages taken from the schema.
Two rules, per target language:

- ``translation_missing``: the source text exists but the translation is
  missing. An error for a required language, information for a recommended
  one, no rule for an optional one.
- ``translation_outdated`` (warning): the source text has changed since the
  translation was last updated.

The second needs a memory of which source text the translation was made
against. It is stored as a checksum per field and language
(``title_translated:en``) in a hidden field (``translation_hashes``), which
the validator :func:`translation_state_validator` updates when a dataset is
saved: if the translation changed in this save, or the checksum is missing,
the checksum is recomputed. Otherwise it is kept -- so that a changed source
text shows up as a deviation. Keys without a language (before 2026-10-01)
apply to the first target language. The rule only compares; it saves nothing.

Values are read in every form they occur in: ckanext-fluent's multilingual
dict or JSON string, the form's separate boxes (``title_translated-en``), and
CKAN's tags (``tag_string`` or ``tags``).
"""

from __future__ import annotations

import hashlib
import json
from typing import List, Mapping

from ckanext.metadata_assistant.localization import _
from ckanext.metadata_assistant.rules.profile import RuleProfile


def source_digest(value: object) -> str:
    """A stable checksum of a source text or a list of keywords."""
    if isinstance(value, (list, tuple)):
        text = ",".join(sorted(str(v).strip().lower() for v in value if str(v).strip()))
    else:
        text = str(value or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _as_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _keywords(value: object) -> list:
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            name = item.get("name") if isinstance(item, dict) else item
            if name and str(name).strip():
                out.append(str(name).strip())
        return out
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


def language_value(dataset: Mapping[str, object], field: str, language: str) -> object:
    """The ``language`` value of a multilingual field, whatever form it has."""
    form_value = dataset.get(f"{field}-{language}")
    if form_value not in (None, ""):
        return form_value
    return _as_dict(dataset.get(field)).get(language) or ""


def source_value(dataset: Mapping[str, object], source_field: str,
                 source_language: str = "") -> object:
    """The source text: a plain field (title, description) or the keywords.

    If the plain field is missing (a fluent form posts only
    ``title_translated-sv``), the source language is read from the multilingual field.
    """
    if source_field == "tag_string":
        return _keywords(dataset.get("tag_string") or dataset.get("tags"))
    value = dataset.get(source_field)
    if not value and source_language:
        value = language_value(dataset, f"{source_field}_translated", source_language)
    return value or ""


def _is_empty(value: object) -> bool:
    if isinstance(value, (list, tuple)):
        return not value
    if isinstance(value, dict):
        return not any(value.values())
    return not str(value or "").strip()


def stored_digests(dataset: Mapping[str, object], state_field: str) -> dict:
    return _as_dict(dataset.get(state_field))


def digest_key(target_field: str, language: str) -> str:
    return f"{target_field}:{language}"


def stored_digest(digests: Mapping[str, str], target_field: str, language: str,
                  first_language: str):
    """A field's digest for a language; a key without a language (written
    before 2026-10-01, when English was the only target) is the first one."""
    key = digest_key(target_field, language)
    if key in digests:
        return digests[key]
    if language == first_language:
        return digests.get(target_field)
    return None


_SEVERITY = {"required": "error", "recommended": "info"}


def check_translations(dataset: Mapping[str, object], profile: RuleProfile):
    from ckanext.metadata_assistant.rules.engine import Finding
    from ckanext.metadata_assistant.localization import language_name

    findings: List[Finding] = []
    if not profile.translation_targets or not profile.target_languages:
        return findings
    digests = stored_digests(dataset, profile.translation_state_field or "")
    first = next(iter(profile.target_languages))
    for language, level in profile.target_languages.items():
        name = language_name(language)
        for source_field, target_field in profile.translation_targets.items():
            source = source_value(dataset, source_field, profile.source_language)
            if _is_empty(source):
                continue
            target = language_value(dataset, target_field, language)
            label = profile.label(source_field)
            if _is_empty(target):
                if level in _SEVERITY:
                    findings.append(Finding(
                        field=target_field, severity=_SEVERITY[level],
                        code="translation_missing",
                        message=(_("'{field}' has no version in {language}. It is required.")
                                 if level == "required" else
                                 _("'{field}' has no version in {language}. It is recommended.")
                                 ).format(field=label, language=name),
                        source=profile.translation_source or profile.name))
                continue
            digest = stored_digest(digests, target_field, language, first)
            if digest is not None and digest != source_digest(source):
                findings.append(Finding(
                    field=target_field, severity="warning", code="translation_outdated",
                    message=_("'{field}' has changed since the version in {language} was "
                              "last updated. Check that the translation is still correct."
                              ).format(field=label, language=name),
                    source=profile.translation_source or profile.name))
    return findings


def translation_state_validator(field, schema):
    """ckanext-scheming validator for the hidden checksum field.

    The field's configuration in the schema (the same field the profile reads
    the language settings from, see rules/profile.py):

        translation_targets: {title_translated: title_translated,
                              notes_translated: notes_translated,
                              keywords_translated: tag_string}
        source_language: sv      # default: the portal's main language (ckan.locale_default)
        target_languages: {en: recommended}

    The key is the translation field, the value the field the source text is read from.
    For a multilingual field it can be the field itself (the source language is read
    from the same dict). ``target_language: en`` (before 2026-10-01) also works.
    """
    targets = field.get("translation_targets") or {}
    from ckanext.metadata_assistant.localization import site_language

    source_language = field.get("source_language") or site_language()   # the whole code, as the fluent fields use it
    languages = list((field.get("target_languages") or {}).keys()) or [
        field.get("target_language", "en")]

    def flat(data):
        """The flat CKAN data as a plain dict, including the form's extras."""
        out = {}
        for key, value in data.items():
            if len(key) == 1:
                out[key[0]] = value
        extras = data.get(("__extras",), {}) or {}
        if isinstance(extras, dict):
            out.update(extras)
        tags = [data[k] for k in sorted(data) if len(k) == 3 and k[0] == "tags" and k[2] == "name"]
        if tags and "tag_string" not in out:
            out["tags"] = tags
        return out

    def validator(key, data, errors, context):
        current = flat(data)
        package = context.get("package")
        old_extras = dict(getattr(package, "extras", {}) or {}) if package else {}
        old_digests = _as_dict(old_extras.get(key[-1]))
        digests = {}
        for target, source in targets.items():
            if source == target:
                src = language_value(current, target, source_language)
            else:
                src = source_value(current, source)
            for language in languages:
                new_value = language_value(current, target, language)
                if _is_empty(new_value):
                    continue
                old_value = _as_dict(old_extras.get(target)).get(language) or ""
                old = stored_digest(old_digests, target, language, languages[0])
                if old is None or not _same(new_value, old_value, source == "tag_string"):
                    digests[digest_key(target, language)] = source_digest(src)
                else:
                    digests[digest_key(target, language)] = old
        data[key] = json.dumps(digests, sort_keys=True) if digests else ""

    return validator


def _same(new_value: object, old_value: object, is_keywords: bool) -> bool:
    """Is the translation unchanged? Keywords are compared as sets, so that
    the form's "a, b" and a stored ["a", "b"] count as the same."""
    if is_keywords:
        return source_digest(_keywords(new_value)) == source_digest(_keywords(old_value))
    return str(new_value or "").strip() == str(old_value or "").strip()
