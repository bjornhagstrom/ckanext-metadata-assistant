"""The deterministic rule engine.

Every ``check_*`` function takes a dataset dict (the same shape as CKAN's
``package_show``) and a :class:`~ckanext.metadata_assistant.rules.profile.RuleProfile`,
and returns a list of :class:`Finding`. :func:`review_dataset` runs all of
them and returns the combined, sorted list. Each check is independently
unit-testable and has no side effects -- nothing here ever mutates the
dataset or talks to CKAN, the filesystem or the network.

These are the unambiguous checks that need no AI: they must give the same
result every time and be traceable to their source (DCAT-AP-SE, or a local
convention).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Mapping, Sequence

from ckanext.metadata_assistant.localization import _
from ckanext.metadata_assistant.rules.profile import RuleProfile
from ckanext.metadata_assistant.rules.data_services import check_data_services, check_hvd_licence, check_hvd_service_contact
from ckanext.metadata_assistant.rules.translations import check_translations
from ckanext.metadata_assistant.rules.links import check_links

Severity = str  # "error" | "warning" | "info" -- kept as plain str for
# simplicity; see _SEVERITY_ORDER below for the fixed set of valid values.

_SEVERITY_ORDER: Mapping[Severity, int] = {"error": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Finding:
    """One thing the rule engine noticed about a dataset.

    Attributes:
        field: The field name the finding is about (for pointing the editor
            at the right form field). May be ``None`` for a dataset-level
            finding that is not tied to one field.
        severity: ``"error"`` (blocks the DCAT-AP-SE requirement),
            ``"warning"`` (recommended but not required), or ``"info"``.
        code: A short, stable machine-readable identifier for the rule that
            produced this finding (e.g. ``"required_field_missing"``), so
            callers (tests, UI, future logging) can key off it without
            parsing the human-readable message.
        message: Human-readable, translated message for the editor.
        source: Where the rule comes from, for traceability -- e.g.
            the active profile's name, e.g. ``"DCAT-AP-SE"``.
        suggestion: A better address for the address the finding is about (only the live address check sets it), which
            the form offers next to the field.
    """

    field: str | None
    severity: Severity
    code: str
    message: str
    source: str
    suggestion: str = ""


def _value(dataset: Mapping[str, object], field_name: str) -> object:
    value = dataset.get(field_name)
    if field_name == "tag_string" and _is_blank(value):
        # A saved dataset (package_show) has ``tags`` and no ``tag_string``, which only the form posts.
        tags = dataset.get("tags")
        if isinstance(tags, (list, tuple)):
            names = [t.get("name") if isinstance(t, dict) else t for t in tags]
            return ", ".join(str(n) for n in names if n)
    return value


def _is_blank(value: object) -> bool:
    """True for None, empty string/list, or a string that is only whitespace."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def _split_keywords(raw: object) -> List[str]:
    """Split a comma-separated tag_string into individual, trimmed keywords.

    Mirrors the help text's instruction ("Separate multiple keywords with
    commas"). Returns an empty list for anything that is not a
    non-empty string.
    """
    if not isinstance(raw, str) or not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def check_required_fields(dataset: Mapping[str, object], profile: RuleProfile) -> List[Finding]:
    """Flag missing or blank required fields as errors."""
    findings = []
    for field_name in profile.required_fields:
        if _is_blank(_value(dataset, field_name)):
            findings.append(
                Finding(
                    field=field_name,
                    severity="error",
                    code="required_field_missing",
                    message=_("'{field}' is required but has no value.").format(
                        field=profile.label(field_name)),
                    source=profile.name,
                )
            )
    return findings


def check_recommended_fields(dataset: Mapping[str, object], profile: RuleProfile) -> List[Finding]:
    """Flag missing or blank recommended fields as warnings."""
    findings = []
    for field_name in profile.recommended_fields:
        if field_name in profile.required_fields:
            continue  # already covered as an error, avoid double-reporting
        if _is_blank(_value(dataset, field_name)):
            findings.append(
                Finding(
                    field=field_name,
                    severity="warning",
                    code="recommended_field_missing",
                    message=_("'{field}' is recommended but has no value.").format(
                        field=profile.label(field_name)),
                    source=profile.name,
                )
            )
    return findings


def check_theme_vocabulary(dataset: Mapping[str, object], profile: RuleProfile) -> List[Finding]:
    """Flag theme values that are not URIs from the configured vocabulary."""
    if not profile.theme_field:
        return []
    raw = _value(dataset, profile.theme_field)
    if _is_blank(raw):
        return []  # absence is handled by the required/recommended checks
    values = raw if isinstance(raw, (list, tuple, set)) else [raw]
    findings = []
    for value in values:
        if value not in profile.theme_allowed_values:
            findings.append(
                Finding(
                    field=profile.theme_field,
                    severity="error",
                    code="theme_not_in_vocabulary",
                    message=_(
                        "'{value}' is not a valid value for '{field}'. Choose one of "
                        "the predefined themes instead of entering your own value."
                    ).format(value=value, field=profile.label(profile.theme_field)),
                    source=profile.name,
                )
            )
    return findings


def check_keywords(dataset: Mapping[str, object], profile: RuleProfile) -> List[Finding]:
    """Flag keyword problems: duplicates, and a single overlong "blob" value.

    A single keyword that itself contains many words and no commas usually
    means the editor typed a phrase instead of separate, comma-separated
    keywords -- the help text explicitly asks for comma separation.
    """
    if not profile.keywords_field:
        return []
    raw = _value(dataset, profile.keywords_field)
    if _is_blank(raw):
        return []

    keywords = raw if isinstance(raw, (list, tuple)) else _split_keywords(raw)
    findings = []

    lowered = [k.lower() for k in keywords]
    seen = set()
    duplicates = set()
    for k in lowered:
        if k in seen:
            duplicates.add(k)
        seen.add(k)
    if duplicates:
        findings.append(
            Finding(
                field=profile.keywords_field,
                severity="warning",
                code="duplicate_keywords",
                message=_("The same keyword appears more than once: {keywords}.").format(
                    keywords=", ".join(sorted(duplicates))),
                source=profile.name,
            )
        )

    if len(keywords) == 1 and len(keywords[0].split()) >= 5:
        findings.append(
            Finding(
                field=profile.keywords_field,
                severity="warning",
                code="keywords_not_separated",
                message=_(
                    "The keyword looks like a whole phrase rather than several "
                    "separate search terms. Separate them with commas, e.g. "
                    "'population, forecast, district'."
                ),
                source=profile.name,
            )
        )

    return findings


def check_description_not_just_title(
    dataset: Mapping[str, object], profile: RuleProfile
) -> List[Finding]:
    """Flag a description that is empty of new information beyond the title."""
    title = _value(dataset, profile.title_field)
    description = _value(dataset, profile.description_field)
    if not isinstance(title, str) or not isinstance(description, str):
        return []
    if not title.strip() or not description.strip():
        return []  # missing-value checks are handled elsewhere

    normalized_title = " ".join(title.split()).strip(".").lower()
    normalized_description = " ".join(description.split()).strip(".").lower()

    if normalized_title == normalized_description:
        return [
            Finding(
                field=profile.description_field,
                severity="warning",
                code="description_repeats_title",
                message=_(
                    "'{description}' only repeats '{title}' word for word. Describe "
                    "the contents, purpose, scope and known limitations instead."
                ).format(description=profile.label(profile.description_field),
                         title=profile.label(profile.title_field)),
                source=profile.name,
            )
        ]

    word_count = len(normalized_description.split())
    if word_count < profile.min_description_words:
        return [
            Finding(
                field=profile.description_field,
                severity="warning",
                code="description_too_short",
                message=_(
                    "'{field}' is very short ({count} words). Describe what the "
                    "dataset contains, why it exists and how it can be used."
                ).format(field=profile.label(profile.description_field), count=word_count),
                source=profile.name,
            )
        ]
    if word_count < profile.description_tip_words:
        return [
            Finding(
                field=profile.description_field,
                severity="info",
                code="description_could_be_longer",
                message=_(
                    "'{field}' is short ({count} words). A longer description helps readers who do not know the "
                    "data: what it contains, how it was produced, how it can be used and what to be careful about."
                ).format(field=profile.label(profile.description_field), count=word_count),
                source=profile.name,
            )
        ]

    return []


# Patterns that strongly suggest licence information was typed into the
# description instead of the dedicated licence field. Intentionally narrow
# (well-known licence domains) to avoid false positives on descriptions that
# merely mention licensing in passing.
_LICENSE_URL_MARKERS = (
    "creativecommons.org",
    "opendatacommons.org",
    "publications.europa.eu/resource/authority/licence",
)


def check_license_information_in_description(
    dataset: Mapping[str, object], profile: RuleProfile
) -> List[Finding]:
    """Flag a likely licence URL pasted into the description instead of the licence field."""
    if not profile.license_field:
        return []
    description = _value(dataset, profile.description_field)
    if not isinstance(description, str) or not description.strip():
        return []

    lowered = description.lower()
    if not any(marker in lowered for marker in _LICENSE_URL_MARKERS):
        return []

    license_value = _value(dataset, profile.license_field)
    if not _is_blank(license_value):
        return []  # licence field is already filled in; the mention is probably fine

    return [
        Finding(
            field=profile.description_field,
            severity="warning",
            code="license_info_in_wrong_field",
            message=_(
                "The description seems to contain a licence link, but '{field}' is "
                "empty. Enter the licence in the licence field instead."
            ).format(field=profile.label(profile.license_field)),
            source=profile.name,
        )
    ]


# All checks, run in this order by review_dataset(). Kept as an explicit
def check_license_missing(dataset: Mapping[str, object], profile: RuleProfile) -> List[Finding]:
    """A dataset without a licence: nobody knows how the data may be used. (When the schema already
    recommends or requires the field, that rule says so and this one stays quiet.)"""
    field_name = profile.license_field
    if not field_name or field_name in profile.recommended_fields or field_name in profile.required_fields:
        return []
    if not _is_blank(_value(dataset, field_name)):
        return []
    return [Finding(
        field=field_name, severity="warning", code="license_missing",
        message=_("'{field}' has no value. Without a licence nobody knows how the data may be used.").format(
            field=profile.label(field_name)),
        source=profile.name)]


MANY_KEYWORDS = 15


def check_keyword_count(dataset: Mapping[str, object], profile: RuleProfile) -> List[Finding]:
    """A single keyword is rarely enough to find a dataset by; very many are a sign of keyword stuffing."""
    if not profile.keywords_field:
        return []
    raw = _value(dataset, profile.keywords_field)
    if _is_blank(raw):
        return []
    keywords = raw if isinstance(raw, (list, tuple)) else _split_keywords(raw)
    label = profile.label(profile.keywords_field)
    if len(keywords) == 1:
        return [Finding(field=profile.keywords_field, severity="info", code="few_keywords",
                        message=_("'{field}' has only one keyword. A few more make the dataset easier to find.").format(
                            field=label), source=profile.name)]
    if len(keywords) > MANY_KEYWORDS:
        return [Finding(field=profile.keywords_field, severity="info", code="many_keywords",
                        message=_("'{field}' has {count} keywords. Keep the ones that describe the data best.").format(
                            field=label, count=len(keywords)), source=profile.name)]
    return []


def check_text_quality(dataset: Mapping[str, object], profile: RuleProfile) -> List[Finding]:
    """Objective slips in the title and description: a title that is all capitals, ends in a file extension or has
    underscores (a file name pasted in), and HTML tags left in the description."""
    import re

    findings: List[Finding] = []
    title = _value(dataset, profile.title_field)
    if isinstance(title, str) and title.strip():
        text = title.strip()
        label = profile.label(profile.title_field)
        if (len(text) > 3 and text.isupper()) or re.search(r"\.(csv|xlsx?|json|zip|shp|xml|geojson)$", text, re.I) \
                or "_" in text:
            findings.append(Finding(
                field=profile.title_field, severity="info", code="title_looks_like_a_file_name",
                message=_("'{field}' looks like a file name or is written in capitals. Write a title a reader "
                          "would understand.").format(field=label), source=profile.name))
    description = _value(dataset, profile.description_field)
    if isinstance(description, str) and re.search(r"<[a-zA-Z/][^>]*>", description) and \
            not getattr(profile, "description_markdown", False):
        findings.append(Finding(
            field=profile.description_field, severity="info", code="description_contains_html",
            message=_("'{field}' contains HTML tags. They are shown as text; write plain text instead.").format(
                field=profile.label(profile.description_field)), source=profile.name))
    return findings


def check_resources_present(dataset: Mapping[str, object], profile: RuleProfile) -> List[Finding]:
    """A saved dataset without any resource has nothing to download or open. Only when the dataset says what
    resources it has (a form draft does not), so an unsaved draft never triggers it."""
    if "resources" not in dataset or dataset.get("resources"):
        return []
    return [Finding(
        field="", severity="warning", code="no_resources",
        message=_("The dataset has no resources. Add a file or a link to the data."), source=profile.name)]


# list (rather than relying on module introspection) so the order is
# obvious and stable regardless of how the module is refactored later.
_ALL_CHECKS: Sequence[Callable[[Mapping[str, object], RuleProfile], List[Finding]]] = (
    check_required_fields,
    check_recommended_fields,
    check_theme_vocabulary,
    check_keywords,
    check_description_not_just_title,
    check_license_information_in_description,
    check_license_missing,
    check_keyword_count,
    check_text_quality,
    check_resources_present,
    check_translations,
    check_data_services,
    check_hvd_service_contact,
    check_hvd_licence,
    check_links,
)


def review_dataset(dataset: Mapping[str, object], profile: RuleProfile) -> List[Finding]:
    """Run every rule check against ``dataset`` and return the combined findings.

    Findings are sorted with errors first, then warnings, then info, and
    are otherwise returned in the order the checks ran (stable sort) so
    output is deterministic and easy to snapshot in tests.
    """
    findings: List[Finding] = []
    for check in _ALL_CHECKS:
        findings.extend(check(dataset, profile))
    return sorted(findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 99))
