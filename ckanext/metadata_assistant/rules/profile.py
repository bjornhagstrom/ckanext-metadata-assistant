"""Rule profiles: what "good metadata" means for a given CKAN schema.

A :class:`RuleProfile` is deliberately not tied to any specific CKAN
instance's schema. It is built from an already-parsed ckanext-scheming schema
dict via :meth:`RuleProfile.from_scheming_dict`, so the same rule engine
serves any portal's schema. What is particular to one catalogue (which fields
are recommended, how the help texts end) is declared by that catalogue's own
schema, in an optional top-level ``metadata_assistant`` block (see
``ckanext.metadata_assistant.profiles``), never in this extension.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Mapping, Optional, Sequence, Tuple


def _site_language():
    from ckanext.metadata_assistant.localization import site_language

    return site_language()


@dataclass(frozen=True)
class RuleProfile:
    """Describes, for one dataset schema, what the rule engine should check.

    Attributes:
        name: Short identifier for the profile, e.g. ``"dcat_ap_se"``. Used
            only in messages/logging, never interpreted by the engine.
        required_fields: Field names that must have a non-empty value.
        recommended_fields: Field names that should have a value, but whose
            absence is only a warning, not an error. ckanext-scheming schemas
            do not mark "recommended" machine-readably (only "required"), so
            this list is supplied explicitly by whoever builds the profile
            for a given schema -- it is not inferred from the schema itself.
        field_labels: Human-readable label per field name, used to make
            finding messages readable without the caller having to look up
            labels itself. Falls back to the raw field name if missing.
        theme_field: Name of the field holding the DCAT theme URI(s), or
            ``None`` if the schema has no controlled theme vocabulary.
        theme_allowed_values: The set of URIs the theme field may contain.
            Ignored if ``theme_field`` is ``None``.
        keywords_field: Name of the free-text keywords field (CKAN's
            ``tag_string`` by convention), or ``None`` to skip keyword
            checks.
        title_field: Name of the title field.
        description_field: Name of the (long-form) description field.
        license_field: Name of the field holding the dataset's licence, if
            any. Used to flag licence information mistakenly typed into the
            description instead.
        min_description_words: A description shorter than this many words
            is flagged as likely too short to be useful. This is a coarse
            heuristic, not a DCAT-AP-SE rule -- tune it per profile.
        description_tip_words: A description shorter than this gets a tip that it could be longer.
    """

    name: str
    required_fields: Tuple[str, ...] = ()
    recommended_fields: Tuple[str, ...] = ()
    field_labels: Mapping[str, str] = field(default_factory=dict)
    theme_field: Optional[str] = None
    theme_allowed_values: FrozenSet[str] = frozenset()
    # 2026-10-01: the schema's label per theme URI, so the AI chooses between
    # "Befolkning och samhälle" rather than bare codes like "SOCI".
    theme_labels: Mapping[str, str] = field(default_factory=dict)
    keywords_field: Optional[str] = None
    title_field: str = "title"
    description_field: str = "notes"
    license_field: Optional[str] = None
    min_description_words: int = 8
    # A description shorter than this gets a tip (not a warning) that it could be longer.
    description_tip_words: int = 25
    # Translations (rules/translations.py; several languages since 2026-10-01).
    # Source field -> the multilingual field holding its translations, e.g.
    # {"title": "title_translated", "tag_string": "keywords_translated"}.
    # Empty = no translation rules. All of it is read from the schema field
    # named by ``translation_state_field``, never set in code.
    translation_targets: Mapping[str, str] = field(default_factory=dict)
    source_language: str = "en"
    # Target language -> "required" | "recommended" | "optional".
    target_languages: Mapping[str, str] = field(default_factory=dict)
    # Target language -> {source term: target term}, for the AI.
    translation_glossary: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    # Target language -> the installation's guidance for the AI.
    translation_instructions: Mapping[str, str] = field(default_factory=dict)
    # 2026-10-01: the form's help text per field, as plain text. Sent to the
    # AI as the rules its suggestions must follow, so the AI and the editor
    # work from the same guidance (and it cannot drift: edit the help text,
    # and the AI's instruction changes with it).
    field_guidance: Mapping[str, str] = field(default_factory=dict)
    translation_state_field: Optional[str] = None
    # The resource field that holds a distribution's data service(s) (``access_services`` in
    # ckanext-dcat), or None when the schema has none. Found in the schema's ``resource_fields``.
    service_field: Optional[str] = None
    # Where the translation rules say their requirement comes from (shown with a finding);
    # empty means the profile's name.
    translation_source: str = ""
    # Whether the description field is edited as Markdown (its form snippet says so, or the schema's block does).
    description_markdown: bool = False

    def label(self, field_name: str) -> str:
        """Human-readable label for ``field_name``, for use in messages."""
        label = self.field_labels.get(field_name, field_name)
        if isinstance(label, Mapping):
            # A schema may give a label per language ({en: Title, sv: Titel}): use the page's language.
            from ckanext.metadata_assistant.localization import pick_language

            label = pick_language(dict(label), default=field_name)
        return str(label)

    @classmethod
    def from_scheming_dict(
        cls,
        name: str,
        schema: Mapping[str, object],
        *,
        recommended_fields: Sequence[str] = (),
        theme_field: Optional[str] = None,
        keywords_field: Optional[str] = "tag_string",
        title_field: str = "title",
        description_field: str = "notes",
        license_field: Optional[str] = None,
        min_description_words: int = 8,
        description_tip_words: int = 25,
        translation_level: str = "optional",
        guidance_markers: Sequence[str] = (),
        translation_source: str = "",
        source_language: Optional[str] = None,
    ) -> "RuleProfile":
        """Build a profile from an already-parsed ckanext-scheming schema.

        ``schema`` is the dict shape ckanext-scheming produces from a
        schema YAML file (e.g. via ``scheming_get_dataset_schema`` or
        ``yaml.safe_load`` of the schema file): a mapping with a
        ``"dataset_fields"`` list of field dicts, each with at least
        ``field_name`` and optionally ``label``, ``required`` and
        ``choices``. This function does not import ``yaml`` or any CKAN
        module itself -- the caller is responsible for parsing the schema
        file; this keeps the rules package free of those dependencies so
        it stays trivially unit-testable.
        """
        dataset_fields = list(schema.get("dataset_fields", []))

        # ckanext-fluent (2026-09-27): a multilingual field such as
        # ``title_translated`` stands for the core field ``title``, which the
        # rules read. It carries the label, and its required language
        # (``fluent_required_language``) makes the core field required --
        # fluent's own ``required: true`` would demand every language.
        def core_name(name: str) -> str:
            return name[: -len("_translated")] if name.endswith("_translated") else name

        field_labels = {}
        for f in dataset_fields:
            if "field_name" not in f:
                continue
            label = f.get("label", f["field_name"])
            field_labels[f["field_name"]] = label
            core = core_name(f["field_name"])
            if core != f["field_name"] and "label" in f:
                field_labels[core] = label
            elif core not in field_labels:
                field_labels[core] = label

        field_guidance = {}
        for f in dataset_fields:
            text = _plain_guidance(f.get("help_text"), guidance_markers)
            if text and "field_name" in f:
                core = core_name(f["field_name"])
                # The multilingual field carries the text; it stands for the
                # core field the rules and the AI work on.
                if core not in field_guidance or core != f["field_name"]:
                    field_guidance[core] = text

        required_fields = tuple(dict.fromkeys(
            core_name(f["field_name"])
            for f in dataset_fields
            if "field_name" in f and (f.get("required") or f.get("fluent_required_language"))
        ))

        theme_allowed_values: FrozenSet[str] = frozenset()
        theme_labels = {}
        if theme_field:
            for f in dataset_fields:
                if f.get("field_name") == theme_field:
                    theme_allowed_values = frozenset(
                        choice["value"] for choice in f.get("choices", [])
                    )
                    for choice in f.get("choices", []):
                        label = choice.get("label")
                        if isinstance(label, Mapping):
                            from ckanext.metadata_assistant.localization import pick_language

                            # Kept with the profile across requests: the portal's main language, not the page's.
                            label = pick_language(dict(label), page=False)
                        if label:
                            theme_labels[choice["value"]] = str(label)
                    break

        translation = _translation_settings(dataset_fields, core_name)
        if not translation:
            translation = _fluent_translation_settings(
                dataset_fields, core_name, keywords_field, source_language, translation_level)
        resource_names = {f.get("field_name") for f in schema.get("resource_fields", [])}
        service_field = "access_services" if "access_services" in resource_names else None
        # A finding about a distribution field (such as the data service) shows the field's label too;
        # a dataset field with the same name keeps its own label.
        for f in schema.get("resource_fields", []):
            if f.get("field_name") and f.get("label"):
                field_labels.setdefault(f["field_name"], f["label"])

        return cls(
            name=name,
            required_fields=required_fields,
            recommended_fields=tuple(recommended_fields),
            field_labels=field_labels,
            theme_field=theme_field,
            theme_allowed_values=theme_allowed_values,
            keywords_field=keywords_field,
            title_field=title_field,
            description_field=description_field,
            license_field=license_field,
            min_description_words=min_description_words,
            description_tip_words=description_tip_words,
            field_guidance=field_guidance,
            service_field=service_field,
            translation_source=translation_source,
            **translation,
            theme_labels=theme_labels,
        )


def _translation_settings(dataset_fields, core_name) -> dict:
    """The translation settings, from the one schema field that holds them.

    That field (``translation_hashes`` in the DCAT-AP-SE schema) stores the
    translation digests and carries ``translation_targets`` (target field ->
    source field), ``source_language``, ``target_languages`` (language ->
    level), ``translation_glossary`` (language -> terms) and
    ``translation_instructions`` (language -> guidance for the AI). The older
    ``target_language: en`` still works, as ``{en: recommended}``.
    """
    for f in dataset_fields:
        targets = f.get("translation_targets")
        if not targets or "field_name" not in f:
            continue
        languages = dict(f.get("target_languages") or {})
        if not languages and f.get("target_language"):
            languages = {f["target_language"]: "recommended"}
        return {
            "translation_targets": {
                core_name(source): target for target, source in targets.items()
            },
            "source_language": f.get("source_language") or _site_language(),
            "target_languages": {
                str(lang): str(level or "recommended") for lang, level in languages.items()
            },
            "translation_glossary": {
                str(lang): dict(terms or {})
                for lang, terms in (f.get("translation_glossary") or {}).items()
            },
            "translation_instructions": {
                str(lang): str(text).strip()
                for lang, text in (f.get("translation_instructions") or {}).items()
            },
            "translation_state_field": f["field_name"],
        }
    return {}


def _fluent_translation_settings(dataset_fields, core_name, keywords_field, source_language,
                                 level="optional") -> dict:
    """Translation settings read from the multilingual (ckanext-fluent) fields themselves.

    For a schema that declares no translation block: every field whose name ends in
    ``_translated`` and that lists ``form_languages`` is a translation target. A tag field (preset
    ``fluent_tags``) is translated from the keywords field, any other from the field of the same
    name without the suffix. The target languages are the ones the fields offer, apart from the
    source language, at ``level`` (default ``optional``: the AI may be asked, no finding is raised; a catalogue can
    set ``recommended`` or ``required`` in its block with ``translation_level``). Without a
    source language nothing is derived.
    """
    if not source_language:
        return {}
    targets, languages = {}, []
    for f in dataset_fields:
        name = f.get("field_name") or ""
        offered = f.get("form_languages")
        if not offered or not name.endswith("_translated"):
            continue
        source = keywords_field if f.get("preset") == "fluent_tags" else core_name(name)
        if not source:
            continue
        targets[source] = name
        languages.extend(str(lang) for lang in offered if str(lang) != source_language)
    if not targets or not languages:
        return {}
    return {
        "translation_targets": targets,
        "source_language": source_language,
        "target_languages": {lang: level for lang in dict.fromkeys(languages)},
    }


def _plain_guidance(help_text, markers: Sequence[str] = ()) -> str:
    """A field's help text as plain guidance: no HTML, and cut at any marker.

    A catalogue can end its help texts with a note for the editor that is not an instruction
    (for example a line saying where a field comes from); it lists such markers in its schema's
    ``metadata_assistant`` block.
    """
    import re

    if isinstance(help_text, Mapping):
        from ckanext.metadata_assistant.localization import pick_language

        help_text = pick_language(dict(help_text), page=False)
    text = re.sub(r"<[^>]+>", "", str(help_text or ""))
    for marker in markers:
        text = text.split(marker, 1)[0]
    return " ".join(text.split())
