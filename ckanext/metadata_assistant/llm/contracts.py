"""Stable request and response contract owned by this extension."""

from __future__ import annotations

import ipaddress
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ThemeChoice(BaseModel):
    """One allowed theme from the active CKAN schema."""

    model_config = ConfigDict(extra="forbid")

    uri: str
    label: str


class LandingPageExtract(BaseModel):
    """What a provider read off an editor-supplied landing page.

    Produced once per URL by a separate, deliberately expensive call, then
    reused as plain input for any number of cheap reviews. Everything in here
    is DATA derived from an untrusted external page -- never instructions.
    """

    model_config = ConfigDict(extra="forbid")

    source_url: str
    # 2026-09-23, found the hard way: an all-optional schema with empty
    # defaults made the model return a completely empty extract every time,
    # even though Google reported URL_RETRIEVAL_STATUS_SUCCESS. Every field
    # was trivially satisfiable by "", and the prompt also says not to invent
    # facts, so empty was the cheapest compliant answer. Requiring real
    # content in the three core fields fixed it outright -- verified against
    # both a content-rich page and a thin one. A page that cannot fill these
    # was not meaningfully read, and failing validation is the right outcome.
    summary: str = Field(min_length=20)
    contents: list[str] = Field(min_length=1)
    suggested_keywords: list[str] = Field(min_length=1)
    # Genuinely optional: plenty of real landing pages say nothing about these.
    coverage: str = ""
    update_frequency: str = ""
    notes: list[str] = Field(default_factory=list)

    @field_validator("contents", "suggested_keywords", "notes")
    @classmethod
    def remove_empty_values(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]

    def has_content(self) -> bool:
        """Did we actually learn anything from the page?

        The page-reading prompt tells the model to leave fields empty rather
        than guess when it cannot read the page, so a structurally valid but
        entirely empty extract means the read failed -- it must not be cached
        and reused as though the page had been read.
        """
        return bool(
            self.summary.strip()
            or self.contents
            or self.suggested_keywords
            or self.coverage.strip()
            or self.update_frequency.strip()
            or self.notes
        )


class MetadataReviewRequest(BaseModel):
    """Only metadata explicitly approved for the semantic review."""

    model_config = ConfigDict(extra="forbid")

    title: str = ""
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    allowed_themes: list[ThemeChoice] = Field(default_factory=list)
    current_theme_uris: list[str] = Field(default_factory=list)
    language: str = "en"   # set by the caller: the language the metadata is written in
    # 2026-10-01: the form's help text for each field the review may suggest
    # (title, notes, tag_string, theme). The suggestions must follow it.
    field_guidance: dict[str, str] = Field(default_factory=dict)
    # Who runs this catalogue: the organisation that owns the dataset here, and the catalogue's own name. The
    # guidelines about not repeating an organisation's name in a title mean these, not an outside publisher's.
    owner_organisation: str = ""
    # Whether the description may be written in Markdown (see markdown.py); else plain text.
    markdown: bool = False
    catalogue_name: str = ""
    landing_page_url: str | None = None
    # When present the provider uses this instead of fetching the page again:
    # one managed fetch per URL, then any number of cheap reviews.
    landing_page_extract: LandingPageExtract | None = None
    # The instruction to the model: the catalogue's own text (admin page), else the default. None means the
    # default; a text, even an empty one, is used as it is. Not sent as part of the material.
    # What the automatic completeness check found in the fields the AI suggests for, as short codes (for example
    # "description_could_be_longer"), so the suggestions can take care of them. Hints, not orders.
    rule_findings: list[str] = Field(default_factory=list, max_length=20)
    catalogue_instructions: str | None = None

    @field_validator("keywords", "current_theme_uris")
    @classmethod
    def remove_empty_values(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]

    @field_validator("landing_page_url")
    @classmethod
    def validate_public_https_url(cls, value: str | None) -> str | None:
        """Accept only URLs suitable for a managed public-web fetch."""
        if value is None or not value.strip():
            return None
        value = value.strip()
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
            return None
        try:
            if not ipaddress.ip_address(hostname).is_global:
                return None
        except ValueError:
            pass
        return value


class FieldSuggestion(BaseModel):
    """A proposed value that an editor may choose to apply."""

    model_config = ConfigDict(extra="forbid")

    field: Literal["title", "notes", "tag_string", "theme"]
    suggested_value: str | list[str]
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class MetadataReviewResponse(BaseModel):
    """Validated semantic review returned by every provider."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    suggestions: list[FieldSuggestion] = Field(default_factory=list)
    questions_for_editor: list[str] = Field(default_factory=list)

    # Set by the provider AFTER validation -- never by the model. Providers
    # strip it from the JSON schema they send, so the model cannot claim it
    # read a page it never saw. None: no landing page was supplied. True: the
    # page was fetched and informed the review. False: a page was supplied but
    # the fetch failed, so the review used only the form's own metadata.
    landing_page_used: bool | None = None

    @field_validator("questions_for_editor")
    @classmethod
    def remove_empty_questions(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]


class TranslationRequest(BaseModel):
    """Metadata to translate from one language into one other. Nothing else
    is sent but the installation's glossary for that language.

    2026-09-27: English for metadata that goes to a national portal;
    2026-10-01: any pair, one request per target language. The
    result is only ever a suggestion that an editor approves.
    """

    model_config = ConfigDict(extra="forbid")

    source_language: str
    target_language: str
    title: str = ""
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    glossary: dict[str, str] = Field(default_factory=dict)
    # The installation's own guidance for this language, e.g. "Use British
    # English" (schema: translation_instructions).
    instructions: str = ""
    # As for the review: None is the default instruction, a text is used as it is.
    catalogue_instructions: str | None = None

    @field_validator("keywords")
    @classmethod
    def remove_empty_keywords(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]

    def is_empty(self) -> bool:
        return not (self.title.strip() or self.description.strip() or self.keywords)


class TranslationResponse(BaseModel):
    """Machine translation of the request's fields. Empty where the source is.

    All three fields are required, with no defaults: the JSON schema sent to
    the model must list them as required. With defaults the schema has no
    ``required`` at all, and a strict-schema model may then answer with the
    title alone -- seen live 2026-09-27 and 2026-09-30 ("only the title got
    translated").
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    description: str
    keywords: list[str]

