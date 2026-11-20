"""Review, translate and read landing pages, through the shared AI connection (ckanext-ai-connector's ``api``).

The connection owns the call: the key, an own server, time limits, the temperature fallback, how a model reads a page. This
module owns what is asked and the shape of the answer (prompts.py, contracts.py), and its own policy for a second attempt:
a review that asked the model to read the landing page is tried again *without* the page (the slow, flaky half of the call),
and a landing page is read once, with no second attempt.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from pydantic import ValidationError

from ckanext.metadata_assistant.localization import _
from ckanext.metadata_assistant.llm.base import ProviderConfigurationError, ProviderError, ProviderResponseError
from ckanext.metadata_assistant.llm.contracts import (
    LandingPageExtract,
    MetadataReviewRequest,
    MetadataReviewResponse,
    TranslationRequest,
    TranslationResponse,
)
from ckanext.metadata_assistant.llm.prompts import (
    LANDING_PAGE_SYSTEM_PROMPT,
    landing_page_prompt,
    landing_page_text_prompt,
    review_system_prompt,
    translation_prompt,
    translation_system_prompt,
    user_prompt,
)

log = logging.getLogger(__name__)

CONSUMER = "metadata_assistant"
PAGE_READ = "page_read"
# The services whose model is handed the landing page inside a review when no extract has been read (measured on Gemini's
# URL context, 2026-09-23). Other models that can read pages read it in a call of its own (read_landing_page) only.
REVIEW_READS_PAGE = ("gemini",)


def _system_message(text: str) -> list[dict[str, str]]:
    """The system message, or none when the catalogue has chosen to send no instruction (providers reject an empty one)."""
    return [{"role": "system", "content": text}] if text and text.strip() else []


def _model_facing_schema() -> dict[str, Any]:
    """The review's response schema minus the fields this extension owns.

    ``landing_page_used`` records whether the page actually informed the review. Only we know that, so the model must never
    be able to set it -- otherwise it could assert it had read a page that was dropped on retry.
    """
    schema = MetadataReviewResponse.model_json_schema()
    schema.get("properties", {}).pop("landing_page_used", None)
    if "required" in schema:
        schema["required"] = [name for name in schema["required"] if name != "landing_page_used"]
    return schema


class MetadataAI:
    """The assistant's AI work over one client (``api.client(CONSUMER, max_attempts=1)``: the attempts are counted here)."""

    def __init__(self, client: Any, *, max_attempts: int = 2, retry_delay_seconds: float = 1.0,
                 sleep_fn: Callable[[float], None] = time.sleep) -> None:
        self.client = client
        self.max_attempts = max(1, max_attempts)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)
        self._sleep = sleep_fn

    @property
    def model(self) -> str:
        return self.client.model

    def can_read_pages(self) -> bool:
        return PAGE_READ in self.client.capabilities

    def _reads_page_in_review(self) -> bool:
        return self.can_read_pages() and self.client.service in REVIEW_READS_PAGE

    def _attempts(self, label: str, call: Callable[[], Any], failure: str, on_retry: Callable[[], None] | None = None):
        """Make ``call``, once more after a transient failure. Raises ProviderError with ``failure``."""
        for attempt in range(1, self.max_attempts + 1):
            try:
                return call()
            except ProviderError as error:
                retryable = bool(getattr(error, "retryable", False))
                # Deliberately omit exception text, request data, URL and API key.
                log.warning("%s attempt failed: attempt=%d/%d status_code=%s retryable=%s",
                            label, attempt, self.max_attempts, getattr(error, "status_code", None), retryable)
                if attempt < self.max_attempts and retryable:
                    if on_retry is not None:
                        on_retry()
                    self._sleep(self.retry_delay_seconds)
                    continue
                if isinstance(error, (ProviderConfigurationError, ProviderResponseError)):
                    raise   # the caller says what was wrong with the answer, or why the connection cannot be used
                status = getattr(error, "status_code", None)
                if status in (500, 502, 503):
                    # Busy or down at the service: say so, or the editor looks for a fault in the settings.
                    failure = "%s %s" % (failure, _("The AI service was busy or unavailable just now; it is not the "
                                                    "settings. Try again in a while."))
                elif status in (408, 504):
                    failure = "%s %s" % (failure, _("The AI service did not answer in time. A faster model, or a longer "
                                                    "time limit on the AI settings page, can help."))
                elif status == 429:
                    failure = "%s %s" % (failure, _("The AI service refused more calls for now (too many calls, or the "
                                                    "account's quota is used up). Try again later."))
                raise ProviderError(failure, status_code=getattr(error, "status_code", None),
                                    retryable=retryable) from error
        raise ProviderError(failure)   # not reached

    # --- review ----------------------------------------------------------------------------------------------------------

    def review(self, request: MetadataReviewRequest) -> MetadataReviewResponse:
        # An extract we already read beats reading the page again: same facts, a fraction of the latency, and none of the
        # managed-fetch flakiness. Order: extract -> the page inside the review -> the form's metadata only.
        state = {"page": bool(request.landing_page_url and request.landing_page_extract is None
                              and self._reads_page_in_review())}
        schema = _model_facing_schema()

        def messages(with_page: bool) -> list[dict[str, str]]:
            return [*_system_message(review_system_prompt(request)),
                    {"role": "user", "content": user_prompt(request, include_landing_page=with_page)}]

        def call():
            if state["page"]:
                try:
                    return self.client.read_page(str(request.landing_page_url), messages(True), schema=schema,
                                                 name="metadata_review", temperature=0.2)
                except ProviderConfigurationError:
                    # The connection will not hand this address to the model (not public https by its stricter rule, e.g.
                    # a bare host name): nothing was sent. Review from the form's metadata, and report the page unused.
                    log.info("The landing page cannot be handed to the model; reviewing without it.")
                    state["page"] = False
            return self.client.structured(messages(False), schema, name="metadata_review", temperature=0.2)

        def drop_page():
            if state["page"]:
                # 2026-09-23: the managed page fetch is the slow and flaky half of this call (measured 39.7-87.7 s per
                # attempt, plus transient 503s). Retrying it with the page would double an already long wait. Drop the page
                # and answer from the form's own metadata: a slightly less informed review in ~30 s rather than nothing.
                state["page"] = False
                log.info("Retrying metadata AI review without landing page context after a slow or failed managed fetch.")

        try:
            result = self._attempts("Metadata AI review", call, _("The AI provider could not complete the review."),
                                    on_retry=drop_page)
            review = MetadataReviewResponse.model_validate(result.data)
        except ProviderResponseError as error:
            raise ProviderResponseError(_("The AI provider returned an invalid review response.")) from error
        except ValidationError:
            # pydantic quotes the model's answer: not chained, so it is not printed with a traceback.
            raise ProviderResponseError(_("The AI provider returned an invalid review response.")) from None
        # Report what actually happened, not what was requested: if the page was dropped on retry, state["page"] is
        # already False. False must mean "we tried and failed", so a model that is never handed the page reports None
        # (not applicable) rather than telling the editor a fetch failed that never ran.
        if request.landing_page_extract is not None:
            used = True   # the page informed this review, just not by fetching it now
        elif request.landing_page_url and self._reads_page_in_review():
            used = state["page"]
        else:
            used = None
        return review.model_copy(update={"landing_page_used": used})

    # --- translation ------------------------------------------------------------------------------------------------------

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        """Translate metadata into another language, as a suggestion only. A plain call, tried again after a transient
        failure."""
        messages = [*_system_message(translation_system_prompt(request)),
                    {"role": "user", "content": translation_prompt(request)}]
        try:
            result = self._attempts(
                "Metadata translation",
                lambda: self.client.structured(messages, TranslationResponse.model_json_schema(),
                                               name="metadata_translation", temperature=0.1),
                _("The AI provider could not translate the texts."))
            return TranslationResponse.model_validate(result.data)
        except (ProviderResponseError, ValidationError):
            raise ProviderResponseError(_("The AI provider returned an invalid translation.")) from None

    # --- landing pages ----------------------------------------------------------------------------------------------------

    def read_landing_page(self, url: str, language: str = "en") -> LandingPageExtract:
        """Read a public landing page once, as reusable structured facts, by the model's own fetch.

        Deliberately separate from review(): this is the slow, fragile call, so it runs once per URL and its result is
        reused for any number of cheap reviews. No second attempt: a failed read falls back to reviewing without the page
        (the caller decides), and retrying the managed fetch is what made the editor wait minutes for nothing.
        """
        if not self.can_read_pages():
            raise ProviderConfigurationError(_("The chosen AI provider cannot read landing pages."))
        messages = [{"role": "system", "content": LANDING_PAGE_SYSTEM_PROMPT},
                    {"role": "user", "content": landing_page_prompt(url, language)}]
        try:
            result = self.client.read_page(url, messages, schema=LandingPageExtract.model_json_schema(),
                                           name="landing_page_extract", temperature=0.2)
        except ProviderResponseError as error:
            log.warning("Landing page read gave an answer in the wrong shape.")
            raise ProviderResponseError(_("The AI provider returned an invalid page summary.")) from error
        except ProviderError as error:
            log.warning("Landing page read failed: status_code=%s", getattr(error, "status_code", None))
            if getattr(error, "retryable", False):
                raise ProviderError(_("The AI service could not read the page just now (it may be busy). Try again in a "
                                      "while.")) from error
            raise ProviderError(_("The landing page could not be read.")) from error
        return self._extract_from(result.data, url)

    def read_landing_page_text(self, url: str, text: str, language: str = "en",
                               timeout: float | None = None) -> LandingPageExtract:
        """The same reading from the page's text, which the portal fetched itself: a plain call without tools, so any model
        can do it (also one that cannot fetch pages, or whose fetch cannot reach the page)."""
        messages = [{"role": "system", "content": LANDING_PAGE_SYSTEM_PROMPT},
                    {"role": "user", "content": landing_page_text_prompt(url, language, text)}]
        try:
            result = self.client.structured(messages, LandingPageExtract.model_json_schema(), name="landing_page_extract",
                                            temperature=0.2,
                                            timeout=timeout if timeout else max(self.client.timeout_seconds, 60.0))
        except ProviderResponseError as error:
            raise ProviderResponseError(_("The AI provider returned an invalid page summary.")) from error
        except ProviderError as error:
            log.warning("Landing page text reading failed: status_code=%s", getattr(error, "status_code", None))
            # The portal has the page: it is the summary that failed, and saying the page could not be read would send the
            # editor looking for a fault in the address.
            if getattr(error, "retryable", False):
                raise ProviderError(_("The portal fetched the page, but the AI service could not summarise it just now "
                                      "(it may be busy). Try again in a while.")) from error
            raise ProviderError(_("The portal fetched the page, but the AI service could not summarise it.")) from error
        return self._extract_from(result.data, url)

    @staticmethod
    def _extract_from(data: Any, url: str) -> LandingPageExtract:
        """The validated extract from the model's answer, or an error when the answer is not worth keeping."""
        try:
            extract = LandingPageExtract.model_validate(data)
        except (TypeError, ValidationError):
            raise ProviderResponseError(_("The AI provider returned an invalid page summary.")) from None
        # Trust our own URL over whatever the model echoed back.
        extract = extract.model_copy(update={"source_url": url})
        if not extract.has_content():
            # 2026-09-23, seen live: the managed fetch can fail while the call itself succeeds, and the model then correctly
            # returns an empty extract rather than inventing facts. Structurally valid, but worthless -- treat it as a
            # failed read so the caller falls back and the editor is told, instead of caching an empty page.
            log.warning("Landing page read returned an empty extract.")
            raise ProviderError(_("The landing page could not be read."))
        return extract
