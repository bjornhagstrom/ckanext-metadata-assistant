"""Markdown in descriptions: whether the assistant writes it, and a plain-text fallback.

``ckanext.metadata_assistant.markdown`` is ``auto`` (default), ``on`` or ``off``, and a sysadmin can change it on the
AI settings page. ``auto`` follows the schema: Markdown when the description field is edited with a Markdown box.
Off means the AI is told to write plain text, and any Markdown that still comes back is turned into plain text.
Markdown is shown on the web but exported as it is typed, so a catalogue that wants page and export to match keeps
it off.
"""

import re

from ckan.plugins import toolkit

OPTION = "ckanext.metadata_assistant.markdown"
MODES = ("auto", "on", "off")


def mode() -> str:
    value = str(toolkit.config.get(OPTION) or "auto").strip().lower()
    return value if value in MODES else "auto"


def enabled(profile) -> bool:
    chosen = mode()
    if chosen == "auto":
        return bool(getattr(profile, "description_markdown", False))
    return chosen == "on"


def plain_text(text: str) -> str:
    """Markdown turned into plain text: emphasis markers, headings, list bullets and links, paragraphs kept."""
    out = []
    for line in str(text or "").replace("\r\n", "\n").split("\n"):
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
        line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line)
        line = re.sub(r"!?\[([^\]]*)\]\(([^)\s]+)[^)]*\)", lambda m: "%s (%s)" % (m.group(1), m.group(2)) if m.group(1) else m.group(2), line)
        line = re.sub(r"(\*\*|__)(.+?)\1", r"\2", line)
        line = re.sub(r"(?<![\w*])[*_]([^*_\n]+?)[*_](?![\w*])", r"\1", line)
        line = re.sub(r"`([^`]*)`", r"\1", line)
        out.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def render(text: str) -> str:
    """The text as the site renders it (CKAN's own, sanitised renderer), for the preview."""
    return str(toolkit.h.render_markdown(str(text or "")[:20000], allow_html=False))


def clean_whitespace(text: str) -> str:
    """Blank space that changes nothing in the rendered text, taken away.

    Spaces at the end of a line are removed where nothing follows on the next line (a blank line, or the end of
    the text) and on lines that hold only spaces; more than one blank line in a row becomes one; the text starts
    and ends at its first and last words. Two spaces at the end of a line that continues on the next line are a
    line break in Markdown, so they stay.
    """
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned = []
    for index, line in enumerate(lines):
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if not line.strip():
            cleaned.append("")
        elif not following.strip():
            cleaned.append(line.rstrip())
        else:
            cleaned.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip("\n")
