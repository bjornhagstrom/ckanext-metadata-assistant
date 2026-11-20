"""The built-in baseline of guidance for the AI: what good metadata looks like, field by field.

The AI follows the catalogue's own guidelines for a field (the help text the editor sees in the form, see
``RuleProfile.field_guidance``). A schema that has no help texts, such as CKAN's own fields, would leave the AI
to its own taste, and it then judges the same dataset differently from one run to the next. This baseline
gives every portal the same starting point; a schema's own help text for a field always replaces it, and a
catalogue can turn it off with ``baseline_guidance: false`` in its schema's ``metadata_assistant`` block.

Written for any catalogue: no place, organisation or portal is named. Keys are the core field names.
"""

from typing import Mapping

BASELINE_GUIDANCE: Mapping[str, str] = {
    "title": (
        "A short, descriptive name, ideally under ten words, that makes the content clear to someone with no "
        "knowledge of the organisation. Do not repeat the name of the organisation that owns the dataset in this "
        "catalogue (owner_organisation) or of the catalogue itself: it would be the same on every dataset and makes "
        "search worse. Another organisation's name stays when it tells whose data this is, for example data "
        "published by someone else. A place name stays when the data is about that place, but is left out when it "
        "only says where the publisher is, since the area has its own field. Never add a name or a place to a title "
        "that has none, and do not widen a title with words the data does not need. Years and formats have their own "
        "fields too; a year may stay when it is the only way to tell similar datasets apart. Avoid internal "
        "project names, unexplained abbreviations, jargon and file names."
    ),
    "notes": (
        "Describe the content clearly for readers who do not know the organisation: what the dataset contains, "
        "why and how it was produced, how the organisation uses it and how others can use it. State important "
        "limits, known limitations and common misunderstandings. Keep everything the description already documents "
        "(resources, attributes, codes, definitions, links, sources) and add to it rather than replace it. Explain "
        "technical terms. Do not just repeat "
        "the title or point to another page. Leave out the licence and the terms of reuse: the licence has its own "
        "field."
    ),
    "tag_string": (
        "Concrete search words in the singular and in lower case, unless the word is a proper name or an "
        "established abbreviation (for example Malmö or PM10), one or a few words per keyword, separated by "
        "commas. The name of a specific place or thing the data is about (a district, a housing area, a park, a "
        "river, a company) is a good keyword. Leave out the name of the organisation that owns the dataset in this "
        "catalogue, and of the whole area the catalogue itself covers, such as its municipality: it would be on every "
        "dataset. A catalogue that wants other names left out says so in its own instruction. Do not repeat the "
        "title, and avoid broad words such as 'data'. A keyword that needs many words belongs in the "
        "description."
    ),
    "url": (
        "Link to a lasting, public page of the publisher about this very dataset, with more information, "
        "documentation or instructions for access. Do not link to a general home page, directly to a file, or "
        "to a page of someone else, and avoid internal addresses that outside users cannot reach."
    ),
    "theme": (
        "Choose the one or two themes that best describe the content. Do not choose all of them when one or "
        "two are enough."
    ),
    "frequency": (
        "The planned or normal update frequency, for example monthly, yearly or as needed. Do not give the "
        "date of the last update here."
    ),
    "spatial_coverage": (
        "The area the data describes, not where the publisher is. Use an established machine-readable "
        "boundary when there is one."
    ),
    "temporal_coverage": (
        "The period or periods the data describes. Leave the end open when the dataset keeps being added to. "
        "It is not the publication or modification date."
    ),
}


def baseline_for(present_fields) -> dict:
    """The baseline texts for the fields a schema has."""
    return {name: text for name, text in BASELINE_GUIDANCE.items() if name in present_fields}
