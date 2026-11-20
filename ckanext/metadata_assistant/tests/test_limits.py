"""Limits shared by every worker (state in Redis). Needs the stack's Redis; uses database 3 so nothing real is touched."""

import os

import pytest

from ckanext.metadata_assistant import limits
from ckanext.metadata_assistant.llm import ProviderError


@pytest.fixture
def redis():
    import redis as redis_lib

    url = os.environ.get("CKAN_REDIS_URL", "redis://redis:6379/1").rsplit("/", 1)[0] + "/3"
    client = redis_lib.Redis.from_url(url)
    try:
        client.ping()
    except Exception:
        pytest.skip("no Redis")
    client.flushdb()
    yield client
    client.flushdb()


class Clock:
    def __init__(self):
        self.now = 1_000_000.0
        self.slept = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class Transient(Exception):
    status_code = 429


def transient_error():
    error = ProviderError("could not")
    error.__cause__ = Transient()
    return error


def test_concurrency_cap_and_expiry(redis):
    assert limits.try_acquire(redis, 2, "a", now=100)
    assert limits.try_acquire(redis, 2, "b", now=100)
    assert not limits.try_acquire(redis, 2, "c", now=100)
    limits.release(redis, "a")
    assert limits.try_acquire(redis, 2, "c", now=100)
    # a slot whose holder died is free again after its time to live
    assert limits.try_acquire(redis, 2, "d", now=100 + limits.SLOT_TTL + 1)
    assert limits.try_acquire(redis, 0, "e", now=100)  # 0 = no limit


def test_pace_allows_n_per_minute_then_waits_for_the_next(redis):
    now = 600.0 + 10
    assert [limits.seconds_until_allowed(redis, 2, now) for _ in range(2)] == [0.0, 0.0]
    assert limits.seconds_until_allowed(redis, 2, now) == pytest.approx(50.0)
    assert limits.seconds_until_allowed(redis, 2, now + 51) == 0.0
    assert limits.seconds_until_allowed(redis, 0, now) == 0.0


def test_breaker_opens_after_repeated_failures_and_a_success_resets_the_count(redis):
    for _ in range(2):
        limits.record_failure(redis, 3, 30)
    assert limits.breaker_open_for(redis) == 0
    limits.record_failure(redis, 3, 30)
    assert 0 < limits.breaker_open_for(redis) <= 30
    redis.delete(limits.KEY + "breaker")
    limits.record_failure(redis, 3, 30)
    limits.record_success(redis)
    limits.record_failure(redis, 3, 30)
    limits.record_failure(redis, 3, 30)
    assert limits.breaker_open_for(redis) == 0


def test_user_quota_counts_active_jobs_and_a_day(redis):
    limits.claim_job(redis, "ann", 2, 0)
    limits.claim_job(redis, "ann", 2, 0)
    with pytest.raises(limits.LimitError):
        limits.claim_job(redis, "ann", 2, 0)
    limits.claim_job(redis, "bob", 2, 0)  # per user
    limits.finish_job(redis, "ann")
    limits.claim_job(redis, "ann", 2, 0)
    limits.claim_job(redis, "cy", 0, 1)
    with pytest.raises(limits.LimitError):
        limits.claim_job(redis, "cy", 0, 1)
    limits.finish_job(redis, "nobody")  # never goes below zero
    assert int(redis.get(limits.KEY + "active:nobody")) == 0


def test_guarded_retries_a_transient_failure_then_succeeds(redis):
    clock, calls = Clock(), []

    def call():
        calls.append(1)
        if len(calls) < 3:
            raise transient_error()
        return "ok"

    config = {limits.PREFIX + "ai_retry_pauses": "5 15 45"}
    assert limits.guarded(call, redis, config, sleep=clock.sleep, clock=clock.time) == "ok"
    assert len(calls) == 3 and clock.slept[:2] == [5.0, 15.0]


def test_guarded_gives_up_after_the_last_pause_and_does_not_retry_other_errors(redis):
    clock = Clock()
    config = {limits.PREFIX + "ai_retry_pauses": "1 2", limits.PREFIX + "ai_breaker_failures": "0"}
    calls = []

    def always():
        calls.append(1)
        raise transient_error()

    with pytest.raises(ProviderError):
        limits.guarded(always, redis, config, sleep=clock.sleep, clock=clock.time)
    assert len(calls) == 3

    calls.clear()

    def bad_answer():
        calls.append(1)
        raise ProviderError("invalid answer")

    with pytest.raises(ProviderError):
        limits.guarded(bad_answer, redis, config, sleep=clock.sleep, clock=clock.time)
    assert len(calls) == 1


def test_open_breaker_answers_at_once_without_calling(redis):
    redis.set(limits.KEY + "breaker", "1", ex=20)
    with pytest.raises(limits.LimitError):
        limits.guarded(lambda: pytest.fail("called"), redis, {})


def test_a_busy_service_makes_the_caller_give_up_after_the_wait(redis):
    clock = Clock()
    config = {limits.PREFIX + "ai_max_concurrent": "1", limits.PREFIX + "ai_slot_wait_seconds": "10"}
    limits.try_acquire(redis, 1, "someone", now=clock.time())
    with pytest.raises(limits.LimitError):
        limits.guarded(lambda: "x", redis, config, sleep=clock.sleep, clock=clock.time)
    assert sum(clock.slept) >= 10


def test_failures_of_a_landing_page_do_not_open_the_breaker(redis):
    clock = Clock()
    config = {limits.PREFIX + "ai_retry_pauses": "1", limits.PREFIX + "ai_breaker_failures": "2"}
    for _ in range(3):
        with pytest.raises(ProviderError):
            limits.guarded(lambda: (_ for _ in ()).throw(transient_error()), redis, config,
                           sleep=clock.sleep, clock=clock.time, breaker=False)
    assert limits.breaker_open_for(redis) == 0
    with pytest.raises(ProviderError):
        limits.guarded(lambda: (_ for _ in ()).throw(transient_error()), redis, config,
                       sleep=clock.sleep, clock=clock.time)
    assert limits.breaker_open_for(redis) > 0


def test_a_crowd_that_waited_for_the_next_minute_is_counted_there(redis):
    clock = Clock()
    clock.now = 600.0 + 30
    config = {limits.PREFIX + "ai_max_per_minute": "1", limits.PREFIX + "ai_slot_wait_seconds": "200"}
    assert limits.guarded(lambda: 1, redis, config, sleep=clock.sleep, clock=clock.time) == 1
    assert limits.guarded(lambda: 2, redis, config, sleep=clock.sleep, clock=clock.time) == 2
    assert limits.guarded(lambda: 3, redis, config, sleep=clock.sleep, clock=clock.time) == 3
    assert sum(clock.slept) >= 90  # three calls at one per minute: two waits of about a minute


def test_limits_that_were_reached_are_counted_for_the_setup_check(redis):
    clock = Clock()
    config = {limits.PREFIX + "ai_retry_pauses": "1", limits.PREFIX + "ai_breaker_failures": "0"}
    with pytest.raises(ProviderError):
        limits.guarded(lambda: (_ for _ in ()).throw(transient_error()), redis, config,
                       sleep=clock.sleep, clock=clock.time)
    with pytest.raises(limits.LimitError):
        limits.claim_job(redis, "bob", 1, 0)
        limits.claim_job(redis, "bob", 1, 0)
    hits = limits.hits_today(redis)
    assert hits["rate_limited"] == 2 and hits["user_quota"] == 1
