"""Limits on AI calls that hold across every worker and web process (state lives in Redis).

* **Concurrency**: at most ``ai_max_concurrent`` calls to the provider at a time. A slot has a time to live, so a
  worker that dies cannot keep one forever.
* **Pace**: at most ``ai_max_per_minute`` calls per minute.
* **Breaker**: ``ai_breaker_failures`` provider failures within a minute stop all calls for ``ai_breaker_seconds``,
  and callers get a clear error at once instead of each waiting for a timeout.
* **User quota**: queued and running jobs per user, and calls per user per day.
* **Retries**: a rate limit (429) or an overloaded provider (503) is retried after the pauses in ``ai_retry_pauses``.

Everything is optional; 0 means no limit. Without Redis nothing here limits anything (a small installation
that runs the AI inside the web request has no use for it).
"""

from __future__ import annotations

import contextlib
import logging
import time
import uuid

from ckan.plugins import toolkit

from ckanext.metadata_assistant.llm import ProviderError
from ckanext.metadata_assistant.localization import _

log = logging.getLogger(__name__)

PREFIX = "ckanext.metadata_assistant."
KEY = "metadata_assistant:"
ACTIVE_TTL = 900  # a job runs at most 5 minutes; a count left by a killed worker is forgotten after this
SLOT_TTL = 300  # seconds a call may hold a slot (longer than any provider timeout)
DEFAULTS = {
    "ai_max_concurrent": 4,
    "ai_max_per_minute": 0,
    "ai_max_jobs_per_user": 3,
    "ai_max_per_user_per_day": 0,
    "ai_breaker_failures": 5,
    "ai_breaker_seconds": 30,
    "ai_slot_wait_seconds": 120,
}
DEFAULT_PAUSES = (5, 15, 45)


class LimitError(ProviderError):
    """A limit stopped the call. The message is safe to show to an editor."""


def setting(name, config=None):
    config = toolkit.config if config is None else config
    try:
        return int(config.get(PREFIX + name, DEFAULTS[name]))
    except (TypeError, ValueError):
        return DEFAULTS[name]


def retry_pauses(config=None):
    config = toolkit.config if config is None else config
    raw = str(config.get(PREFIX + "ai_retry_pauses", "") or "").replace(",", " ").split()
    try:
        pauses = tuple(max(0.0, float(p)) for p in raw)
    except ValueError:
        pauses = ()
    return pauses or DEFAULT_PAUSES


def connection():
    """The Redis connection CKAN uses, or None when there is none."""
    try:
        from ckan.lib.redis import connect_to_redis

        client = connect_to_redis()  # builds a pool; it does not connect, so ask once
        client.ping()
        return client
    except Exception as error:  # no Redis configured or reachable
        log.warning("Metadata assistant: no Redis, limits are off (%s)", type(error).__name__)
        return None


# -- limits reached (shown in the setup check and by `queue`, so an administrator sees when a stronger model or plan
# is needed instead of the extension working around the service) -------------------------------------------------

HIT_KINDS = ("rate_limited", "breaker_opened", "busy", "user_quota")


def note_hit(redis, kind, now=None):
    now = time.time() if now is None else now
    key = "%shits:%s" % (KEY, time.strftime("%Y%m%d", time.gmtime(now)))
    try:
        redis.hincrby(key, kind, 1)
        redis.expire(key, 3 * 86400)
    except Exception:
        pass


def hits_today(redis, now=None):
    """``{kind: count}`` for today (UTC), only the kinds that happened."""
    now = time.time() if now is None else now
    raw = redis.hgetall("%shits:%s" % (KEY, time.strftime("%Y%m%d", time.gmtime(now)))) or {}
    return {(k.decode() if isinstance(k, bytes) else k): int(v) for k, v in raw.items()}


# -- concurrency -----------------------------------------------------------------------------------------------

_ACQUIRE = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
if tonumber(ARGV[3]) > 0 and redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then return 0 end
redis.call('ZADD', KEYS[1], ARGV[1] + ARGV[2], ARGV[4])
return 1
"""


def try_acquire(redis, maximum, token, now=None, ttl=SLOT_TTL):
    now = time.time() if now is None else now
    return bool(redis.eval(_ACQUIRE, 1, KEY + "slots", now, ttl, maximum, token))


def release(redis, token):
    redis.zrem(KEY + "slots", token)


def in_use(redis, now=None):
    now = time.time() if now is None else now
    redis.zremrangebyscore(KEY + "slots", "-inf", now)
    return redis.zcard(KEY + "slots")


# -- pace ------------------------------------------------------------------------------------------------------

def seconds_until_allowed(redis, per_minute, now=None):
    """Count a call in the current minute. 0 when it may go ahead now, else seconds to wait for the next minute."""
    if per_minute <= 0:
        return 0.0
    now = time.time() if now is None else now
    window = int(now // 60)
    key = KEY + "pace:%d" % window
    count = redis.incr(key)
    redis.expire(key, 120)
    if count <= per_minute:
        return 0.0
    redis.decr(key)
    return max(0.1, (window + 1) * 60 - now)


# -- breaker ---------------------------------------------------------------------------------------------------

def breaker_open_for(redis):
    """Seconds left while the breaker is open, else 0."""
    left = redis.ttl(KEY + "breaker")
    return max(0, left) if left and left > 0 else 0


def record_failure(redis, threshold, open_seconds, now=None):
    if threshold <= 0:
        return
    now = time.time() if now is None else now
    key = KEY + "failures"
    redis.zadd(key, {uuid.uuid4().hex: now})
    redis.zremrangebyscore(key, "-inf", now - 60)
    redis.expire(key, 120)
    if redis.zcard(key) >= threshold:
        note_hit(redis, "breaker_opened")
        redis.set(KEY + "breaker", "1", ex=max(1, open_seconds))
        redis.delete(key)
        log.warning("Metadata assistant: the AI breaker is open for %ds", open_seconds)


def record_success(redis):
    redis.delete(KEY + "failures")


# -- user quota ------------------------------------------------------------------------------------------------

def claim_job(redis, user, max_jobs, max_per_day, now=None):
    """Count a new job for the user, or raise :class:`LimitError`. Call :func:`finish_job` when it ends."""
    now = time.time() if now is None else now
    day = time.strftime("%Y%m%d", time.gmtime(now))
    if max_per_day > 0:
        per_day = "%sday:%s:%s" % (KEY, day, user)
        if redis.incr(per_day) > max_per_day:
            redis.decr(per_day)
            note_hit(redis, "user_quota")
            raise LimitError(_("The daily limit of AI requests is reached. Try again tomorrow."))
        redis.expire(per_day, 2 * 86400)
    if max_jobs > 0:
        active = "%sactive:%s" % (KEY, user)
        if redis.incr(active) > max_jobs:
            redis.decr(active)
            if max_per_day > 0:
                redis.decr(per_day)
            note_hit(redis, "user_quota")
            raise LimitError(_("You already have %d AI requests waiting or running. Wait for one to finish.") % max_jobs)
        redis.expire(active, ACTIVE_TTL)


def finish_job(redis, user):
    key = "%sactive:%s" % (KEY, user)
    if redis.decr(key) < 0:
        redis.set(key, 0, ex=ACTIVE_TTL)


# -- the guarded call ------------------------------------------------------------------------------------------

_TRANSIENT_STATUS = frozenset({408, 429, 500, 502, 503, 504})


def _transient(error):
    if getattr(error, "retryable", None) is True:   # ckanext-ai-connector's AIError says it
        return True
    code = getattr(error, "status_code", None)
    if code is None:
        code = getattr(getattr(error, "response", None), "status_code", None)
    if code in _TRANSIENT_STATUS:
        return True
    name = type(error).__name__.lower()
    return any(part in name for part in ("timeout", "ratelimit", "serviceunavailable"))


def is_transient(error):
    """True for a rate limit, a timeout or an overloaded provider (found on the error or its cause)."""
    seen = 0
    while error is not None and seen < 5:
        if _transient(error):
            return True
        error, seen = error.__cause__ or error.__context__, seen + 1
    return False


@contextlib.contextmanager
def slot(redis, config=None, sleep=time.sleep, clock=time.time, breaker=True, inline=False):
    """Hold one concurrency slot (and pass the pace and the breaker) while the provider is called."""
    # Inside a web request nobody waits: the server would kill the request, and a place held by a killed
    # request stays taken until it expires.
    wait = 0 if inline else setting("ai_slot_wait_seconds", config)
    maximum = setting("ai_max_concurrent", config)
    open_for = breaker_open_for(redis) if breaker else 0
    if open_for:
        raise LimitError(_("The AI service is not answering right now. Try again in %d seconds.") % open_for)
    per_minute = setting("ai_max_per_minute", config)
    deadline = clock() + wait
    delay = seconds_until_allowed(redis, per_minute, now=clock())
    while delay:  # counted again in the next minute, so a crowd that waited cannot all pass at once
        if clock() + delay > deadline:
            note_hit(redis, "busy")
            raise LimitError(_("The AI service is busy. Try again in a minute."))
        sleep(delay)
        delay = seconds_until_allowed(redis, per_minute, now=clock())
    token = uuid.uuid4().hex
    while not try_acquire(redis, maximum, token, now=clock()):
        if clock() >= deadline:
            note_hit(redis, "busy")
            raise LimitError(_("The AI service is busy. Try again in a minute."))
        sleep(0.5)
    try:
        yield
    finally:
        release(redis, token)


def guarded(call, redis=None, config=None, sleep=time.sleep, clock=time.time, breaker=True, pauses=None,
            inline=False):
    """Run ``call()`` within the limits, retrying a transient failure after the configured pauses.

    ``call`` raises :class:`ProviderError`. Transient failures count towards the breaker, unless ``breaker`` is
    false: reading a landing page fails because of that page (it is slow, or down), which says nothing about the
    AI service.
    """
    redis = connection() if redis is None else redis
    if redis is None:
        return call()
    pauses = retry_pauses(config) if pauses is None else tuple(pauses)
    threshold, open_seconds = setting("ai_breaker_failures", config), setting("ai_breaker_seconds", config)
    attempt = 0
    while True:
        with slot(redis, config, sleep=sleep, clock=clock, breaker=breaker, inline=inline):
            try:
                result = call()
            except (ProviderError, toolkit.ValidationError) as error:
                if isinstance(error, LimitError) or not is_transient(error):
                    raise
                note_hit(redis, "rate_limited")
                if breaker:
                    record_failure(redis, threshold, open_seconds)
                if attempt >= len(pauses):
                    raise
                pause = pauses[attempt]
            else:
                if breaker:
                    record_success(redis)
                return result
        attempt += 1
        log.info("Metadata assistant: transient AI failure, trying again in %ss", pause)
        sleep(pause)
