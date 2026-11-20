"""Interface texts: English source, translated by CKAN when it can.

2026-10-01. The rule engine and the providers also run without a CKAN
request (unit tests, the CLI), so translation is looked up lazily and
falls back to the English text. Babel extracts every ``_("...")`` call;
see babel.cfg and ``i18n/``.
"""


def _(message: str) -> str:
    try:
        from ckan.plugins.toolkit import _ as translate

        return translate(message)
    except Exception:
        return message


def ui_language() -> str:
    """The language the page is shown in, or "en" outside a request."""
    try:
        from ckan.plugins.toolkit import h

        return h.lang() or "en"
    except Exception:
        return "en"


def site_language() -> str:
    """The portal's main language (``ckan.locale_default``), or "en"."""
    try:
        from ckan.plugins.toolkit import config

        return str(config.get("ckan.locale_default") or "en")
    except Exception:
        return "en"


def pick_language(texts, *, page: bool = True, default: str = "") -> str:
    """One text from a ``{language: text}`` mapping: the page's language (when ``page``), then the portal's main language,
    then English, then the first non-empty one. ``sv_SE`` also matches ``sv``. Not a mapping: the value as text."""
    if not isinstance(texts, dict):
        return str(texts) if texts else default
    wanted = ([ui_language()] if page else []) + [site_language(), "en"]
    for code in wanted:
        for key in (code, code.split("_")[0]):
            if texts.get(key):
                return str(texts[key])
    return str(next((value for value in texts.values() if value), default))


def language_name(code: str, in_language: str = "") -> str:
    """A language's name, e.g. "engelska" for "en" on a Swedish page.

    From Babel's locale data, so no language name is written by hand.
    Falls back to the code for a language Babel does not know.
    """
    try:
        from babel import Locale

        name = Locale.parse(code.replace("-", "_")).get_display_name(
            Locale.parse((in_language or ui_language()).replace("-", "_")))
    except Exception:
        return code
    return name or code
