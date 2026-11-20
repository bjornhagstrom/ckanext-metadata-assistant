"""Fetch a public landing page ourselves and reduce it to the text a person would read.

The AI services can fetch a page for us (Gemini's URL context, Claude's web fetch), but a page that blocks their fetchers stays unread
(seen: several municipal sites, which an AI service's fetch cannot reach). Fetching it from the portal's own server works with any model, and is
the backup when the service's fetch fails (``landing_page_fetch = auto``) or the way for every model (``own``).

The address comes from an editor, so the fetch is as careful as the link check's: https only, no address that is not public (checked for
every hop of a redirect), a time limit, a size limit, and only text and HTML.
"""
import codecs
import ipaddress
import logging
import re
import socket
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import requests
from ckan.plugins import toolkit

from ckanext.metadata_assistant.localization import _

log = logging.getLogger(__name__)

ALLOWED_SCHEMES = ("https",)
MAX_BYTES = 2_000_000
MAX_REDIRECTS = 5
TOTAL_SECONDS = 20.0
TEXT_LIMIT = 12000          # characters of page text given to the AI
MIN_TEXT = 200              # characters: less is a page that needs a browser (its text is built by JavaScript), or an error page
DEFAULT_USER_AGENT = "ckanext-metadata-assistant/1.0"
_TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "application/xml", "text/xml")


class PageFetchError(Exception):
    """The page could not be read; the message is for the editor.

    ``service_may_help`` says whether it is worth asking the AI service to try: yes for a page that needs a browser (no text), a
    document, or a site that keeps robots out; no for a page that does not exist (404, 410), where the service would only guess.
    """

    def __init__(self, message, service_may_help=True):
        super().__init__(message)
        self.service_may_help = service_may_help


def is_public(host):
    """True when every address the host resolves to is a public one (a host that does not resolve is not)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    for info in infos:
        try:
            if not ipaddress.ip_address(info[4][0].split("%")[0]).is_global:
                return False
        except ValueError:
            return False
    return bool(infos)


def user_agent():
    """Who is asking, with where to reach us: some sites (Wikipedia) refuse an agent that gives no address, and a firewall one
    that gives none at all."""
    configured = toolkit.config.get("ckanext.metadata_assistant.page_user_agent")
    if configured:
        return str(configured)
    site = str(toolkit.config.get("ckan.site_url") or "").strip().rstrip("/")
    return "%s (+%s)" % (DEFAULT_USER_AGENT, site or "https://github.com/bjornhagstrom/ckanext-metadata-assistant")


def _accept_language(language=None):
    """``language`` (the language the metadata is written in) first, else the portal's main language, then English."""
    from ckanext.metadata_assistant.localization import site_language

    language = (language or site_language()).replace("_", "-")
    base = language.split("-")[0].lower()
    return "en" if base == "en" else "%s,en;q=0.7" % language


def fetch_html(url, language=None):
    """The page's HTML as text. Raises :class:`PageFetchError`."""
    started = time.monotonic()
    # No compression (so the size limit is the size on the wire) and no proxy, .netrc or other settings from the environment (the address check
    # above is made against the name as the portal resolves it).
    headers = {"User-Agent": user_agent(), "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.8",
               "Accept-Language": _accept_language(language), "Accept-Encoding": "identity"}
    session = requests.Session()
    session.trust_env = False
    for _hop in range(MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        if parts.scheme not in ALLOWED_SCHEMES or not parts.hostname or parts.username or parts.password:
            raise PageFetchError(_("The landing page must be a public https address."), service_may_help=False)
        if not is_public(parts.hostname):
            raise PageFetchError(_("The landing page is not on a public address (an internal or private network, or a name that does not exist). "
                                   "Such pages are not read."), service_may_help=False)
        left = TOTAL_SECONDS - (time.monotonic() - started)
        if left <= 1:
            raise PageFetchError(_("The landing page took too long to answer."))
        try:
            response = session.get(url, headers=headers, timeout=(5, min(10, left)), allow_redirects=False, stream=True)
        except requests.RequestException as error:
            log.info("Landing page fetch failed: %s", type(error).__name__)
            raise PageFetchError(_("The landing page could not be reached.")) from error
        try:
            if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
                target = response.headers.get("Location")
                if not target:
                    raise PageFetchError(_("The landing page could not be reached."))
                url = urljoin(url, target)
                continue
            if response.status_code != 200:
                raise PageFetchError(_("The landing page answered with an error ({code}).").format(code=response.status_code),
                                     service_may_help=response.status_code not in (404, 410))
            kind = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if kind and kind not in _TEXT_TYPES:
                raise PageFetchError(_("The landing page is not a web page or a text."))
            body = bytearray()
            while len(body) <= MAX_BYTES:
                # One read of whatever has arrived (not "wait for 64 kB"), so the time limit is checked often.
                chunk = response.raw.read1(65536, decode_content=True)
                if not chunk:
                    break
                body.extend(chunk)
                if time.monotonic() - started > TOTAL_SECONDS:
                    raise PageFetchError(_("The landing page took too long to answer."))
            return _decode(bytes(body[:MAX_BYTES]), response.headers.get("Content-Type") or "")
        except requests.RequestException as error:
            raise PageFetchError(_("The landing page could not be reached.")) from error
        finally:
            response.close()
    raise PageFetchError(_("The landing page forwards too many times."))


def _decode(body, content_type):
    """The text of the body. The encoding is the one the header names, else the one a ``<meta>`` in the first 2 kB names, else UTF-8
    (``requests`` would take ISO-8859-1 for any ``text/*`` without a charset, which spoils å, ä and ö on a UTF-8 page). A name Python does not
    know is not an error."""
    match = re.search(r"charset\s*=\s*[\"']?([\w.:-]+)", content_type, re.I)
    if not match:
        match = re.search(rb"<meta[^>]+charset\s*=\s*[\"']?([\w.:-]+)", body[:2048], re.I)
    name = match.group(1) if match else "utf-8"
    if isinstance(name, bytes):
        name = name.decode("ascii", errors="ignore")
    try:
        encoding = codecs.lookup(name).name
    except LookupError:
        encoding = "utf-8"
    return body.decode(encoding, errors="replace")


# What is not part of what the page says: scripts and styles, and the furniture around the content.
_SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "nav", "header", "footer", "aside", "button", "select"}
_BLOCK = {"p", "div", "section", "article", "main", "li", "ul", "ol", "tr", "table", "br", "h1", "h2", "h3", "h4", "h5", "h6",
          "dd", "dt", "dl", "blockquote", "pre", "figure", "figcaption", "details", "summary"}


class _Reader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.parts = []
        self._skip = 0
        self._in_title = False
        self._main = 0          # inside <main> or <article>: a <header> there is the content's own (its heading)
        self._title_done = False
        self._skipped = []      # the skipped tags that are open

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title" and not self._title_done and not self._skip:
            self._in_title = True
        elif tag == "meta":
            name = (attrs.get("name") or attrs.get("property") or "").lower()
            if name in ("description", "og:description") and not self.description:
                self.description = (attrs.get("content") or "").strip()
        if tag in ("main", "article"):
            self._main += 1
            # Content starts here: a menu left open earlier must not hide it.
            self._skip, self._skipped = 0, []
        if tag in _SKIP and not (tag == "header" and self._main):
            self._skip += 1
            self._skipped.append(tag)
        if tag in _BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self._in_title = False
            self._title_done = True
        if tag in ("main", "article") and self._main:
            self._main -= 1
        if tag in self._skipped:
            self._skipped.remove(tag)
            self._skip = max(self._skip - 1, 0)
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def page_text(html, limit=TEXT_LIMIT):
    """The text of a page: its title, description and the content, without scripts, menus and footers."""
    reader = _Reader()
    try:
        reader.feed(html)
        reader.close()
    except Exception:  # a page that is not valid HTML: use what was read
        pass
    lines, previous = [], None
    for raw in "".join(reader.parts).splitlines():
        line = " ".join(raw.split())
        if len(line) < 2 or line == previous:
            continue
        lines.append(line)
        previous = line
    head = []
    if reader.title.strip():
        head.append("Title: " + " ".join(reader.title.split()))
    if reader.description:
        head.append("Description: " + " ".join(reader.description.split()))
    text = "\n".join(head + ([""] if head else []) + lines).strip()
    return text[:limit].rstrip()


def fetch_text(url, language=None):
    """The text of the page at ``url``. Raises :class:`PageFetchError`, also for a page with no text to read."""
    text = page_text(fetch_html(url, language))
    if len(text) < MIN_TEXT:
        raise PageFetchError(_("The landing page has no text to read."))
    return text
