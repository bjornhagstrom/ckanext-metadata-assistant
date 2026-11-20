"""The portal's own fetch of a landing page (2026-10-21): the backup for an AI service whose fetch cannot read the page."""

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import Mock, patch

import pytest

from ckan.plugins import toolkit

from ckanext.metadata_assistant import actions, admin_settings, page_fetch
from ckanext.metadata_assistant.llm import LandingPageExtract, ProviderError

PAGE = """<!doctype html><html><head><title>Cykelräknare</title>
<meta name="description" content="Timvärden från 17 räknare."><script>var secret = 'do not show';</script><style>p{}</style></head>
<body><nav>Meny Start Kontakt</nav><header>Webbplatsens huvud</header>
<main><h1>Cykelräknare i kommunen</h1><p>Datamängden innehåller timvärden från 17 cykelräknare som är placerade längs kommunens huvudstråk för cykel och gång. Värdena räknas per timme, dygnet runt, och publiceras som öppna data tillsammans med en beskrivning av hur räknarna fungerar och hur de kalibreras.</p>
<ul><li>Uppdateras dagligen</li><li>Uppdateras dagligen</li></ul><table><tr><td>Täckning</td><td>Hela kommunen</td></tr></table></main>
<footer>Sidfot Cookies</footer></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):
        _Handler.seen.append(self.headers.get("User-Agent"))
        routes = {
            "/page": (200, "text/html; charset=utf-8", PAGE.encode()),
            "/moved": (302, "text/html", b""),
            "/loop": (302, "text/html", b""),
            "/missing": (404, "text/html", b"no"),
            "/data.bin": (200, "application/octet-stream", b"\x00\x01"),
            "/big": (200, "text/html", b"<p>" + b"x" * (page_fetch.MAX_BYTES + 5000) + b"</p>"),
            "/empty": (200, "text/html", b"<html><body><script>1</script></body></html>"),
            "/nocharset": (200, "text/html", PAGE.encode("utf-8")),
            "/oddcharset": (200, "text/html; charset=utf8mb4", PAGE.encode("utf-8")),
            "/latin1": (200, "text/html", PAGE.replace("<head>", '<head><meta charset="iso-8859-1">').encode("iso-8859-1", errors="replace")),
            "/webforms": (200, "text/html; charset=utf-8", ("<html><body><form runat='server'><main><h1>Cykelräknare</h1><p>Timvärden från 17 räknare i kommunen, räknade per timme och publicerade som öppna data med en beskrivning av hur räknarna fungerar, var de är placerade och hur de kalibreras, så att värdena går att jämföra över åren.</p></main></form></body></html>").encode("utf-8")),
            "/headerinarticle": (200, "text/html; charset=utf-8", b"<html><body><nav>Meny <ul><li>Start</li></ul><article><header><h1>Rubriken i artikeln</h1></header><p>Texten i artikeln handlar om cykelr\xc3\xa4knare som r\xc3\xa4knar passerande cyklar per timme och publiceras som \xc3\xb6ppna data, med en l\xc3\xa4ngre beskrivning av hur r\xc3\xa4knarna \xc3\xa4r placerade och fungerar.</p></article><footer>Sidfot</footer></body></html>"),
            "/svgtitle": (200, "text/html; charset=utf-8", b"<html><head><title>Riktiga titeln</title></head><body><svg><title>Sok-ikon</title></svg><p>Brodtext som ar tillrackligt lang for att raknas som en riktig sida med innehall, och som fortsatter en god bit forbi tvahundra tecken for att inte tas for ett tomt skal av en sida som byggs i webblasaren med JavaScript.</p></body></html>"),
            "/redirect-to-http": (302, "text/html", b""),
            "/redirect-without-location": (302, "text/html", b""),
            "/drip": (200, "text/html", b"<p>" + b"slow " * 40 + b"</p>"),
        }
        status, kind, body = routes.get(self.path, (404, "text/html", b""))
        self.send_response(status)
        if self.path == "/moved":
            self.send_header("Location", "/page")
        if self.path == "/loop":
            self.send_header("Location", "/loop")
        if self.path == "/redirect-to-http":
            self.send_header("Location", "http://example.org/page")
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.path == "/drip":
            for index in range(len(body)):
                self.wfile.write(body[index:index + 1])
                self.wfile.flush()
                time.sleep(0.05)
            return
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server(monkeypatch):
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(page_fetch, "is_public", lambda host: True)
    monkeypatch.setattr(page_fetch, "ALLOWED_SCHEMES", ("http", "https"))
    _Handler.seen.clear()
    yield "http://127.0.0.1:%d" % httpd.server_address[1]
    httpd.shutdown()


def test_the_text_of_a_page_is_what_a_person_reads(server):
    text = page_fetch.fetch_text(server + "/page")
    assert text.startswith("Title: Cykelräknare\nDescription: Timvärden från 17 räknare.")
    assert "Cykelräknare i kommunen" in text and "17 cykelräknare" in text and "Hela kommunen" in text
    assert text.count("Uppdateras dagligen") == 1                       # a repeated line once
    for left_out in ("do not show", "Meny", "Webbplatsens huvud", "Sidfot", "p{}"):
        assert left_out not in text


def test_the_fetch_says_who_it_is_and_follows_a_redirect(server):
    assert "Title: Cykelräknare" in page_fetch.fetch_text(server + "/moved")
    assert _Handler.seen and all(agent and "ckanext-metadata-assistant" in agent for agent in _Handler.seen)   # never no User-Agent


@pytest.mark.ckan_config("ckanext.metadata_assistant.page_user_agent", "Test-Agent/9")
def test_the_user_agent_can_be_set(server):
    page_fetch.fetch_text(server + "/page")
    assert _Handler.seen == ["Test-Agent/9"]


@pytest.mark.parametrize("path", ["/missing", "/data.bin", "/empty", "/loop"])
def test_a_page_that_cannot_be_read_is_an_error_with_a_reason(server, path):
    with pytest.raises(page_fetch.PageFetchError):
        page_fetch.fetch_text(server + path)


def test_a_huge_page_is_cut_at_the_size_limit_and_the_text_is_limited(server):
    assert len(page_fetch.fetch_html(server + "/big")) <= page_fetch.MAX_BYTES
    assert len(page_fetch.fetch_text(server + "/big")) <= page_fetch.TEXT_LIMIT


def test_the_encoding_is_utf8_without_a_charset_and_an_unknown_one_is_not_an_error(server):
    for path in ("/nocharset", "/oddcharset"):
        assert "Cykelräknare" in page_fetch.fetch_text(server + path)        # never "CykelrÃ¤knare"
    assert "Cykelräknare" in page_fetch.fetch_text(server + "/latin1")     # a <meta charset> is followed


def test_what_a_person_reads_stays_when_the_page_is_built_in_unusual_ways(server):
    assert "Cykelräknare" in page_fetch.fetch_text(server + "/webforms")                 # the whole body in a <form>
    text = page_fetch.fetch_text(server + "/headerinarticle")                            # the heading is in a <header>, in the article
    assert "Rubriken i artikeln" in text and "Texten i artikeln" in text and "Meny" not in text and "Sidfot" not in text
    text = page_fetch.fetch_text(server + "/svgtitle")                                   # an icon's title is not the page's
    assert text.startswith("Title: Riktiga titeln\n") and "Sok-ikon" not in text


def test_a_menu_left_open_does_not_hide_the_content():
    text = page_fetch.page_text("<html><body><nav>Meny<main><h1>Cykelräknare i kommunen</h1><p>Timvärden från 17 räknare.</p></main></body></html>")
    assert "Cykelräknare i kommunen" in text and "Timvärden" in text and "Meny" not in text


def test_a_slow_server_is_given_up_on_at_the_time_limit(server, monkeypatch):
    monkeypatch.setattr(page_fetch, "TOTAL_SECONDS", 1.0)
    started = time.monotonic()
    with pytest.raises(page_fetch.PageFetchError):
        page_fetch.fetch_html(server + "/drip")
    assert time.monotonic() - started < 4


def test_a_redirect_to_http_or_without_a_location_is_an_error(server):
    monkeypatch_schemes = page_fetch.ALLOWED_SCHEMES
    page_fetch.ALLOWED_SCHEMES = ("https",)
    try:
        with pytest.raises(page_fetch.PageFetchError):
            page_fetch.fetch_html(server + "/redirect-to-http")     # the server itself is http: refused at once
    finally:
        page_fetch.ALLOWED_SCHEMES = monkeypatch_schemes
    with pytest.raises(page_fetch.PageFetchError):
        page_fetch.fetch_html(server + "/redirect-without-location")


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "::ffff:10.0.0.1", "fe80::1", "169.254.169.254", "0.0.0.0", "192.168.1.1", "100.64.0.1", "2130706433"])
def test_addresses_that_are_not_public_are_not_public(host):
    assert page_fetch.is_public(host) is False


def test_a_public_address_is_public_and_a_name_that_does_not_resolve_is_not():
    assert page_fetch.is_public("93.184.216.34") is True
    assert page_fetch.is_public("no-such-host.invalid") is False


@pytest.mark.parametrize("url", [
    "http://example.org/",                  # not https
    "https://user:pw@example.org/",         # credentials in the address
    "https://localhost/",
    "https://127.0.0.1/",
    "https://192.168.1.10/page",
    "https://10.0.0.5/",
    "https://[::1]/",
    "https://169.254.169.254/latest/meta-data/",
])
def test_an_address_that_is_not_a_public_https_page_is_refused_before_any_request(url):
    with patch.object(page_fetch.requests.Session, "get") as get:
        with pytest.raises(page_fetch.PageFetchError):
            page_fetch.fetch_html(url)
    assert not get.called


def test_a_redirect_to_a_private_address_is_refused(monkeypatch):
    redirect = Mock(is_redirect=True, status_code=302, headers={"Location": "https://10.0.0.5/secret"})
    redirect.close = Mock()
    monkeypatch.setattr(page_fetch, "is_public", lambda host: host != "10.0.0.5")
    with patch.object(page_fetch.requests.Session, "get", return_value=redirect) as get:
        with pytest.raises(page_fetch.PageFetchError):
            page_fetch.fetch_html("https://example.org/start")
    assert get.call_count == 1                                           # the private address was never requested


# --- Which fetch is used --------------------------------------------------------------------------------------------

def _extract(summary):
    return LandingPageExtract(source_url="https://example.org/d", summary=summary, contents=["a"], suggested_keywords=["b"])


class _Provider:
    def __init__(self, service=None, text=None):
        self.calls = []
        self._service, self._text = service, text

    def read_landing_page(self, url, language="en"):
        self.calls.append("service")
        if self._service is None:
            raise ProviderError("The landing page could not be read.")
        return self._service

    def read_landing_page_text(self, url, text, language="en"):
        self.calls.append("text:" + text[:5])
        return self._text


def _run(provider, mode, monkeypatch, fetch=lambda url, language=None: "Page text of the page"):
    monkeypatch.setattr("ckanext.metadata_assistant.ai.assistant", lambda *a, **k: provider)
    monkeypatch.setitem(toolkit.config, admin_settings.PREFIX + "landing_page_fetch", mode)
    monkeypatch.setattr(page_fetch, "fetch_text", fetch)
    return actions.execute_landing_page({"kind": "landing", "url": "https://example.org/d", "language": "en"})


def _refuse(code="the page needs a browser", may_help=True):
    def refuse(url, language=None):
        raise page_fetch.PageFetchError(code, service_may_help=may_help)
    return refuse


def test_a_landing_page_is_read_for_its_own_purpose(monkeypatch):
    asked = []
    working = _Provider(service=None, text=_extract("read from the portal's own fetch"))
    _run(working, "own", monkeypatch)
    monkeypatch.setattr("ckanext.metadata_assistant.ai.assistant", lambda *a, **k: asked.append(a) or working)
    actions.execute_landing_page({"kind": "landing", "url": "https://example.org/d", "language": "en"})
    assert asked == [("landing_page",)]


def test_the_portals_fetch_asks_for_the_page_in_the_metadata_language(monkeypatch):
    asked = []
    working = _Provider(service=None, text=_extract("read from the portal's own fetch"))
    _run(working, "own", monkeypatch, fetch=lambda url, language=None: asked.append(language) or "Page text of the page")
    assert asked == ["en"]   # the spec's language, the one the review is written in


def test_auto_uses_the_portals_fetch_first_and_the_service_when_the_portal_cannot_read_the_page(monkeypatch):
    working = _Provider(service=_extract("read by the AI service's fetch"), text=_extract("read from the portal's own fetch"))
    assert _run(working, "auto", monkeypatch)["summary"] == "read from the portal's own fetch" and working.calls == ["text:Page "]
    needs_browser = _Provider(service=_extract("read by the AI service's fetch"), text=_extract("read from the portal's own fetch"))
    assert _run(needs_browser, "auto", monkeypatch, fetch=_refuse())["summary"] == "read by the AI service's fetch"
    assert needs_browser.calls == ["service"]                              # the model was not asked to read text that was never fetched


def test_a_page_that_does_not_exist_is_not_given_to_the_service_which_would_only_guess(monkeypatch):
    provider = _Provider(service=_extract("read by the AI service's fetch"), text=_extract("read from the portal's own fetch"))
    with pytest.raises(toolkit.ValidationError) as error:
        _run(provider, "auto", monkeypatch, fetch=_refuse("The landing page answered with an error (404).", may_help=False))
    assert "404" in str(error.value.error_dict["ai"]) and provider.calls == []


def test_provider_only_never_fetches_and_own_never_asks_the_service(monkeypatch):
    service = _Provider(service=_extract("read by the AI service's fetch"), text=_extract("read from the portal's own fetch"))
    assert _run(service, "provider", monkeypatch)["summary"] == "read by the AI service's fetch" and service.calls == ["service"]
    own = _Provider(service=_extract("read by the AI service's fetch"), text=_extract("read from the portal's own fetch"))
    assert _run(own, "own", monkeypatch)["summary"] == "read from the portal's own fetch" and own.calls == ["text:Page "]
    with pytest.raises(toolkit.ValidationError):
        _run(_Provider(service=None, text=_extract("x" * 30)), "own", monkeypatch, fetch=_refuse("no text"))


def test_the_default_user_agent_says_where_to_reach_us(monkeypatch):
    assert page_fetch.user_agent().startswith("ckanext-metadata-assistant/") and "(+http" in page_fetch.user_agent()
    monkeypatch.setitem(toolkit.config, "ckan.site_url", "https://data.example.org/")
    assert page_fetch.user_agent() == "ckanext-metadata-assistant/1.0 (+https://data.example.org)"


def test_a_page_with_almost_no_text_is_a_page_that_needs_a_browser(server):
    with pytest.raises(page_fetch.PageFetchError) as error:
        page_fetch.fetch_text(server + "/empty")
    assert error.value.service_may_help is True
    with pytest.raises(page_fetch.PageFetchError) as missing:
        page_fetch.fetch_text(server + "/missing")
    assert missing.value.service_may_help is False                            # 404: nothing for the service to read


def test_the_setting_is_one_of_three_and_defaults_to_auto(monkeypatch):
    assert admin_settings.landing_page_fetch_mode() == "auto"
    monkeypatch.setitem(toolkit.config, admin_settings.PREFIX + "landing_page_fetch", "nonsense")
    assert admin_settings.landing_page_fetch_mode() == "auto"
    with pytest.raises(toolkit.Invalid):
        admin_settings._landing_page_fetch("nonsense")


# --- A page read ahead of time (when the edit form opens): protection for the web processes ---------------------------

class _FakeRedis:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    def delete(self, key):
        self.data.pop(key, None)


def _ahead_spec(url="https://example.org/d"):
    return {"kind": "landing", "url": url, "language": "sv", "ahead": True, "inline": True}


def test_a_read_ahead_runs_one_at_a_time_and_a_failed_page_is_left_alone_for_a_while(monkeypatch):
    from ckanext.metadata_assistant import jobs

    redis = _FakeRedis()
    monkeypatch.setattr(jobs.limits, "connection", lambda: redis)
    calls = []

    def run(spec):
        calls.append(spec["url"])
        raise toolkit.ValidationError({"ai": ["The landing page answered with an error (503)."]})

    monkeypatch.setattr(jobs, "run_spec", run)
    redis.data[jobs.AHEAD_LOCK] = "1"                                       # another read ahead is going
    assert jobs._read_ahead_inline(_ahead_spec()) == {"state": "none"} and calls == []
    del redis.data[jobs.AHEAD_LOCK]
    with pytest.raises(toolkit.ValidationError):
        jobs._read_ahead_inline(_ahead_spec())                               # it runs, fails, and the lock is released
    assert calls == ["https://example.org/d"] and jobs.AHEAD_LOCK not in redis.data
    assert jobs._read_ahead_inline(_ahead_spec()) == {"state": "none"}      # the same page is not tried again at once
    assert len(calls) == 1
    with pytest.raises(toolkit.ValidationError):
        jobs._read_ahead_inline(_ahead_spec("https://example.org/other"))    # another page is


def test_a_read_ahead_uses_the_portals_own_fetch_only_and_a_short_limit(monkeypatch):
    seen = {}

    class Provider:
        def read_landing_page(self, url, language="en"):
            seen["service"] = True
            return _extract("read by the AI service's fetch")

        def read_landing_page_text(self, url, text, language="en", timeout=None):
            seen["timeout"] = timeout
            return _extract("read from the portal's own fetch")

    monkeypatch.setattr("ckanext.metadata_assistant.ai.assistant", lambda *a, **k: Provider())
    monkeypatch.setitem(toolkit.config, admin_settings.PREFIX + "landing_page_fetch", "auto")
    monkeypatch.setattr(page_fetch, "fetch_text", lambda url, language=None: "Page text of the page")
    assert actions.execute_landing_page(_ahead_spec())["summary"] == "read from the portal's own fetch"
    assert seen == {"timeout": actions.AHEAD_AI_SECONDS}
    # and when the portal cannot read the page, the AI service is NOT asked (it can take 180 s of a web process)
    def refuse(url, language=None):
        raise page_fetch.PageFetchError("the page needs a browser", service_may_help=True)

    monkeypatch.setattr(page_fetch, "fetch_text", refuse)
    with pytest.raises(toolkit.ValidationError):
        actions.execute_landing_page(_ahead_spec())
    assert "service" not in seen
