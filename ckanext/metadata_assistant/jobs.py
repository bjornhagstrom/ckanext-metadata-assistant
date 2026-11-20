"""AI requests as background jobs, so a web worker never waits for the AI.

The page starts a job (``metadata_assistant_job_start``) and asks how it is going
(``metadata_assistant_job_status``). The web request does the quick part: access, the request for the AI
(``actions.prepare_*``), the caches and the user's quota. A worker process (``ckan metadata-assistant worker``)
does the slow part (``actions.execute_*``) within the limits in :mod:`limits`.

``ckanext.metadata_assistant.jobs``: ``auto`` (default) queues a request when a worker is listening and
otherwise runs it in the web request, exactly as before; ``on`` always queues; ``off`` never does.

Two queues: ``metadata_assistant`` for editors who are waiting and ``metadata_assistant_bulk`` for
``review-all``, listed second by the worker so an editor's request is taken before any waiting bulk request (one
already running is not interrupted).
"""

from __future__ import annotations

import datetime
import logging

import ckan.plugins.toolkit as toolkit

from ckanext.metadata_assistant import actions, cache, limits
from ckanext.metadata_assistant.llm import ProviderError
from ckanext.metadata_assistant.localization import _

log = logging.getLogger(__name__)

QUEUE = "metadata_assistant"
BULK_QUEUE = "metadata_assistant_bulk"
KINDS = ("landing", "review", "translate")
JOB_TIMEOUT = 300  # seconds a job may run (a landing page read can take minutes)
RESULT_TTL = 900  # seconds the answer waits to be fetched


# -- running a spec (in the web request without a worker, else in the worker) ----------------------------------

def _landing(url, language, fresh=False, inline=False, ahead=False):
    """A page read: ``{"extract", "fetched_at"}``, from the cache, else read (within the limits) and remembered.

    ``ahead``: read when the edit form opens, which nobody asked for: only the portal's own fetch and a short limit (see ``execute_landing_page``).
    """
    if not fresh:
        hit = cache.landing_get(url, language)
        if hit:
            return hit
    extract = limits.guarded(lambda: actions.execute_landing_page(
        {"kind": "landing", "url": url, "language": language, "ahead": ahead}),
        breaker=False, pauses=() if inline else None, inline=inline)
    return cache.landing_put(url, language, extract)


# A page read ahead of time (when an edit form opens) runs in the web request when no worker listens, and there are only a few web processes:
# one such read at a time, and a page that failed is not tried again for a while, so that opening forms cannot take the site's processes.
AHEAD_LOCK = "metadata_assistant:landing_ahead"
AHEAD_LOCK_SECONDS = 70
AHEAD_FAIL_SECONDS = 600


def _read_ahead_inline(spec):
    """Read a page ahead of time in the web request, if it is allowed now: ``{"state": "none"}`` when another is going or this page failed lately."""
    redis = limits.connection()
    failed_key = "metadata_assistant:landing_failed:" + cache._landing_key(spec["url"], spec["language"])
    if redis is not None:
        try:
            if redis.get(failed_key) or not redis.set(AHEAD_LOCK, "1", nx=True, ex=AHEAD_LOCK_SECONDS):
                return {"state": "none"}
        except Exception as error:   # Redis away: the read is allowed (the limits are not there either)
            log.warning("Read-ahead gate unavailable: %s", type(error).__name__)
            redis = None
    try:
        return _done(run_spec(spec))
    except limits.LimitError as error:
        raise toolkit.ValidationError({"ai": [str(error)]}) from error
    except (ProviderError, toolkit.ValidationError):
        if redis is not None:
            try:
                redis.set(failed_key, "1", ex=AHEAD_FAIL_SECONDS)
            except Exception:
                pass
        raise
    finally:
        if redis is not None:
            try:
                redis.delete(AHEAD_LOCK)
            except Exception:
                pass


def _pauses(spec):
    """No waiting between tries inside a web request (the server would kill it); a worker may wait."""
    return () if spec.get("inline") else None


def run_spec(spec):
    """The slow part of a request; returns the same data as the synchronous action would."""
    kind = spec["kind"]
    if kind == "landing":
        return _landing(spec["url"], spec["language"], fresh=bool(spec.get("fresh")), inline=bool(spec.get("inline")), ahead=bool(spec.get("ahead")))
    if kind == "translate":
        return limits.guarded(lambda: actions.execute_translation(spec), pauses=_pauses(spec), inline=bool(spec.get('inline')))
    request = dict(spec["request"])
    if spec.get("read_landing") and request.get("landing_page_url") and not request.get("landing_page_extract"):
        try:  # prepared in advance: without the page rather than not at all
            request["landing_page_extract"] = _landing(request["landing_page_url"], request["language"])["extract"]
        except (ProviderError, toolkit.ValidationError) as error:
            log.info("Review prepared without the landing page: %s", error)
    spec = dict(spec, request=request)
    result = limits.guarded(lambda: actions.execute_review(spec), pauses=_pauses(spec), inline=bool(spec.get('inline')))
    if spec.get("digest") and spec.get("package_id"):
        cache.review_put(spec["digest"], spec["package_id"], result)
    return result


def _message(error):
    if isinstance(error, toolkit.ValidationError):
        for messages in error.error_dict.values():
            if messages:
                return str(messages[0])
    return str(error) or _("The AI request failed.")


def run_job(spec, user=""):
    """The job function the worker runs. Returns ``{"ok": True, "result": ...}`` or ``{"ok": False, "error": ...}``."""
    redis = limits.connection()
    try:
        return {"ok": True, "result": run_spec(spec)}
    except (ProviderError, toolkit.ValidationError) as error:
        return {"ok": False, "error": _message(error)}
    except Exception:  # never a stack trace for the editor; the log has it
        log.exception("Metadata assistant job failed")
        return {"ok": False, "error": _("The AI request failed.")}
    finally:
        if redis is not None and user:
            limits.finish_job(redis, user)


# -- queue ----------------------------------------------------------------------------------------------------

def mode():
    value = str(toolkit.config.get("ckanext.metadata_assistant.jobs", "auto") or "auto").strip().lower()
    return value if value in ("auto", "on", "off") else "auto"


ALIVE_SECONDS = 90  # our worker beats every ~45 s (worker_ttl=60); one silent for longer has died


def workers_listening(queue_name=QUEUE):
    """How many job workers listen on the queue and have shown a sign of life lately (0 without Redis).

    Workers must be started with ``ckan metadata-assistant worker``: a worker started otherwise beats too rarely
    to be counted.
    """
    try:
        from ckan.lib.jobs import get_queue
        from rq import Worker

        now = datetime.datetime.now(datetime.timezone.utc)
        alive = 0
        for worker in Worker.all(queue=get_queue(queue_name)):
            beat = worker.last_heartbeat
            if beat is None:
                continue
            if beat.tzinfo is None:
                beat = beat.replace(tzinfo=datetime.timezone.utc)
            if (now - beat).total_seconds() <= ALIVE_SECONDS:
                alive += 1
        return alive
    except Exception as error:
        log.warning("Cannot count job workers: %s", type(error).__name__)
        return 0


def queueing():
    setting = mode()
    return setting == "on" or (setting == "auto" and workers_listening() > 0)


def enqueue(spec, user, queue_name=QUEUE, title=""):
    from ckan.lib import jobs as ckan_jobs

    return ckan_jobs.enqueue(
        run_job, kwargs={"spec": spec, "user": user}, title=title or "metadata assistant %s" % spec["kind"],
        queue=queue_name, rq_kwargs={"timeout": JOB_TIMEOUT, "result_ttl": RESULT_TTL, "failure_ttl": RESULT_TTL})


def _position(job):
    try:
        from ckan.lib.jobs import get_queue, remove_queue_name_prefix

        return get_queue(remove_queue_name_prefix(job.origin)).get_job_position(job)
    except Exception:
        return None


# -- actions --------------------------------------------------------------------------------------------------

def prepare(context, data_dict):
    kind = data_dict.get("kind")
    if kind not in KINDS:
        raise toolkit.ValidationError({"kind": [_("Unknown kind of AI request.")]})
    if kind == "landing":
        spec = actions.prepare_landing_page(context, data_dict)
    elif kind == "review":
        spec = actions.prepare_review(context, data_dict)
        from ckanext.metadata_assistant import ai

        spec["model"] = ai.model()
        spec["digest"] = cache.review_digest(spec["request"], spec["model"], spec["package_id"])
    else:
        spec = actions.prepare_translation(context, data_dict)
    return spec


def _done(result, cached=False, prepared_at=None):
    return {"state": "done", "result": result, "cached": cached,
            "prepared_at": prepared_at.replace(microsecond=0).isoformat() + "Z" if prepared_at else None}


def metadata_assistant_job_start(context, data_dict):
    """Start an AI request (``kind``: ``landing``, ``review`` or ``translate``; the other keys are those of the
    synchronous actions). Returns ``{"state": "done", "result": ...}`` when it was answered at once (from a cache, or
    run here when no worker listens), ``{"state": "queued", "job_id": ..., "position": ...}`` when a worker has it,
    or ``{"state": "none"}`` for ``cache_only`` without a prepared answer. ``fresh`` skips the caches.
    """
    from ckanext.metadata_assistant import ai

    user = (context.get("user") or "") if context else ""
    reason = ai.problem()   # the shared AI connection (ckanext-ai-connector) cannot be used: say so, queue nothing
    quiet = bool(data_dict.get("cache_only") or data_dict.get("ahead"))
    if reason and quiet:
        return {"state": "none"}   # asked by the panel on its own (a prepared answer, a read nobody asked for): fail quietly
    try:
        spec = prepare(context, data_dict)  # access is checked here; nothing is spent before that
    except ProviderError as error:   # e.g. without ckanext-ai-connector the settings cannot be read
        raise toolkit.ValidationError({"ai": [reason or str(error)]}) from error
    fresh = bool(data_dict.get("fresh"))
    cache_only = bool(data_dict.get("cache_only"))
    kind = spec["kind"]
    if kind == "review" and not fresh:
        hit = cache.review_get(spec["digest"])
        if hit:
            return _done(hit[0], cached=True, prepared_at=hit[1])
    if kind == "landing" and not fresh:
        hit = cache.landing_get(spec["url"], spec["language"])
        if hit:
            return _done(hit, cached=True)
    if cache_only:
        return {"state": "none"}
    if reason:
        raise toolkit.ValidationError({"ai": [reason]})
    if kind == "landing":
        spec["fresh"] = fresh
        spec["ahead"] = bool(data_dict.get("ahead"))

    if not queueing():
        spec["inline"] = True
        if spec.get("ahead"):
            return _read_ahead_inline(spec)
        try:
            return _done(run_spec(spec))
        except limits.LimitError as error:
            raise toolkit.ValidationError({"ai": [str(error)]}) from error
    redis = limits.connection()
    if redis is not None and user:
        try:
            limits.claim_job(redis, user, limits.setting("ai_max_jobs_per_user"),
                             limits.setting("ai_max_per_user_per_day"))
        except limits.LimitError as error:
            raise toolkit.ValidationError({"ai": [str(error)]}) from error
    try:
        job = enqueue(spec, user)
    except Exception:
        if redis is not None and user:
            limits.finish_job(redis, user)
        raise
    return {"state": "queued", "job_id": job.id, "position": _position(job)}


@toolkit.side_effect_free
def metadata_assistant_job_status(context, data_dict):
    """How a job is going: ``queued`` (with ``position``), ``running``, ``done`` (with ``result``) or ``failed``
    (with ``error``). Only for the person who started it, and sysadmins."""
    from ckan.authz import is_sysadmin
    from ckan.lib import jobs as ckan_jobs

    user = (context.get("user") or "") if context else ""
    if not user:
        raise toolkit.NotAuthorized()
    job_id = str(data_dict.get("job_id") or "")
    if not job_id:
        raise toolkit.ValidationError({"job_id": ["Missing value"]})
    try:
        job = ckan_jobs.job_from_id(job_id)
    except KeyError:
        raise toolkit.ObjectNotFound(_("The AI request is no longer there. Start it again."))
    if job.kwargs.get("user") != user and not is_sysadmin(user):
        raise toolkit.NotAuthorized()
    status = job.get_status()
    if status == "finished":
        outcome = job.return_value() or {}
        if outcome.get("ok"):
            return {"state": "done", "result": outcome.get("result")}
        return {"state": "failed", "error": outcome.get("error") or _("The AI request failed.")}
    if status in ("failed", "stopped", "canceled"):
        return {"state": "failed", "error": _("The AI request did not finish. Try again.")}
    if status == "started":
        return {"state": "running"}
    return {"state": "queued", "position": _position(job)}


# -- bulk -----------------------------------------------------------------------------------------------------

def enqueue_prepared_review(context, dataset_id):
    """Queue a review of a saved dataset to be prepared in advance. Returns ``"queued"``, ``"prepared"`` (up to date) or ``"waiting"`` (queued by an earlier run, not served yet). Used by ``ckan metadata-assistant review-all``."""
    spec = prepare(context, {"kind": "review", "id": dataset_id})
    if cache.review_get(spec["digest"]):
        return "prepared"
    redis = limits.connection()
    # Once per text: a run repeated before the first has been served would pay twice.
    if redis is not None and not redis.set("%squeued:%s" % (limits.KEY, spec["digest"]), "1", nx=True, ex=3600):
        return "waiting"
    spec["read_landing"] = True
    enqueue(spec, "", queue_name=BULK_QUEUE, title="prepare review %s" % dataset_id)
    return "queued"
