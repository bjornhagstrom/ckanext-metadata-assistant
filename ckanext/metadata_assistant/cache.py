"""Caches that let many people share one AI call.

* **Landing page extract**, per address, in Redis for ``landing_page_cache_hours`` (default 6). Ten editors
  opening datasets that point at the same page cost one read of it.
* **Review**, per dataset, in the database: the latest review with the digest of everything the AI was given.
  It is a hit only while that is unchanged. A review prepared in advance (``ckan metadata-assistant review-all``)
  is such an entry. Nothing here is metadata: an editor still reads and applies every suggestion.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging

from ckan import model as ckan_model
from ckan.plugins import toolkit

from ckanext.metadata_assistant import limits
from ckanext.metadata_assistant.model import ReviewCache, _now

log = logging.getLogger(__name__)

LANDING_HOURS = 6


# -- landing page ----------------------------------------------------------------------------------------------

def _landing_key(url, language, model=None):
    """The cache key of a page read: the address, the language and the model that reads pages (another model reads another
    summary, API 2 lets the landing page have a model of its own)."""
    if model is None:
        from ckanext.metadata_assistant import ai

        model = ai.model(ai.LANDING_PAGE)
    return limits.KEY + "landing:" + hashlib.sha256(("%s|%s|%s" % (language, url, model)).encode("utf-8")).hexdigest()


def landing_get(url, language, redis=None):
    """``{"extract": ..., "fetched_at": ISO time}`` for a page read earlier, or None."""
    redis = limits.connection() if redis is None else redis
    if redis is None:
        return None
    try:
        raw = redis.get(_landing_key(url, language))
        return json.loads(raw) if raw else None
    except Exception as error:
        log.warning("Landing page cache read failed: %s", type(error).__name__)
        return None


def landing_put(url, language, extract, redis=None, hours=None):
    """Remember a read; returns the entry (the time it was fetched is part of it)."""
    entry = {"extract": extract, "fetched_at": datetime.datetime.now(datetime.timezone.utc).replace(
        microsecond=0).isoformat()}
    redis = limits.connection() if redis is None else redis
    if redis is None:
        return entry
    hours = _hours() if hours is None else hours
    if hours <= 0:
        return entry
    try:
        redis.set(_landing_key(url, language), json.dumps(entry), ex=int(hours * 3600))
    except Exception as error:
        log.warning("Landing page cache write failed: %s", type(error).__name__)
    return entry


def _hours():
    try:
        return float(toolkit.config.get(limits.PREFIX + "landing_page_cache_hours", LANDING_HOURS))
    except (TypeError, ValueError):
        return LANDING_HOURS


# -- review ----------------------------------------------------------------------------------------------------

def review_digest(request, model_name, package_id=""):
    """A digest of what the AI is given. The page extract itself is left out (the address is in), but whether
    there is one is not: a review made before the page was read must not answer one made with it. The dataset's
    id is in, so a review is never shown for another dataset."""
    body = {k: v for k, v in dict(request).items() if k != "landing_page_extract"}
    body["with_landing_page_extract"] = bool(dict(request).get("landing_page_extract"))
    text = json.dumps({"request": body, "model": model_name, "package": package_id or ""},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def review_get(digest):
    """``(result, created)`` for a digest, or ``None``."""
    try:
        row = ckan_model.Session.get(ReviewCache, digest)
    except Exception as error:  # the table is missing: a cache must never break the review
        ckan_model.Session.rollback()
        log.warning("Review cache read failed: %s", type(error).__name__)
        return None
    if row is None:
        return None
    return json.loads(row.result), row.created


def review_put(digest, package_id, result):
    """Keep this as the latest review of the dataset (older ones are dropped)."""
    session = ckan_model.Session
    try:
        if package_id:
            session.query(ReviewCache).filter(
                ReviewCache.package_id == package_id, ReviewCache.digest != digest).delete()
        row = session.get(ReviewCache, digest)
        payload = json.dumps(result, ensure_ascii=False)
        if row is None:
            session.add(ReviewCache(digest=digest, package_id=package_id or "", result=payload))
        else:
            row.result = payload
            row.created = _now()
        session.commit()
    except Exception as error:  # a cache must never break the review
        session.rollback()
        log.warning("Review cache write failed: %s", type(error).__name__)


def prepared_count():
    """How many reviews are ready (0 when the table is missing, which the setup check reports)."""
    try:
        return ckan_model.Session.query(ReviewCache).count()
    except Exception:
        ckan_model.Session.rollback()
        return 0
