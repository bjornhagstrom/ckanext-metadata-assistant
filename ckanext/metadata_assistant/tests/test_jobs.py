"""AI requests as jobs: the caches, the quota, running without a worker, running through the queue, and who may
ask how a job went. The AI itself is replaced by a fake; Redis is the real one, database 3 with queues of their own."""

import pytest
from ckan import model as ckan_model
from ckan.plugins import toolkit
from ckan.tests import factories

from ckanext.metadata_assistant import actions, cache, jobs, limits
from ckanext.metadata_assistant.model import ReviewCache
from ckanext.metadata_assistant.llm import MetadataReviewResponse, ProviderError

import os

TEST_REDIS = os.environ.get("CKAN_REDIS_URL", "redis://redis:6379/1").rsplit("/", 1)[0] + "/3"

pytestmark = [
    pytest.mark.ckan_config("ckan.site_id", "metadata_assistant_test"),
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "metadata_assistant ai_connector"),
    pytest.mark.usefixtures("with_plugins", "metadata_assistant_db", "clean_redis"),
]


@pytest.fixture
def metadata_assistant_db(clean_db, migrate_db_for):
    migrate_db_for("metadata_assistant")


@pytest.fixture
def clean_redis(monkeypatch):
    """Limits and caches go to database 3 and the queues get a site id of their own, so the real dev Redis (its
    keys, its queues, a running dev worker) is never touched."""
    import redis as redis_lib

    redis = redis_lib.Redis.from_url(TEST_REDIS)
    try:
        redis.ping()
    except Exception:
        pytest.skip("no Redis")
    monkeypatch.setattr(limits, "connection", lambda: redis)
    from ckan.plugins.toolkit import config

    monkeypatch.setitem(config, "ckan.site_id", "metadata_assistant_test")
    def wipe():
        from ckan.lib.jobs import get_queue

        for key in redis.scan_iter(limits.KEY + "*"):
            redis.delete(key)
        for name in (jobs.QUEUE, jobs.BULK_QUEUE):
            get_queue(name).empty()  # test jobs must not wait for a real worker

    wipe()
    yield redis
    wipe()


class FakeProvider:
    def __init__(self):
        self.reviews = 0
        self.fail = None

    def review(self, request):
        self.reviews += 1
        if self.fail:
            raise self.fail
        return MetadataReviewResponse(summary="Review %d of %s" % (self.reviews, request.title))


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()

    monkeypatch.setattr("ckanext.metadata_assistant.ai.assistant", lambda *a, **k: fake)
    monkeypatch.setattr("ckanext.metadata_assistant.ai.model", lambda *a: "fake/model")
    monkeypatch.setattr("ckanext.metadata_assistant.ai.problem", lambda *a: None)
    monkeypatch.setattr(jobs, "workers_listening", lambda queue_name=jobs.QUEUE: 0)
    return fake


def _editor_and_dataset():
    user = factories.User()
    org = factories.Organization(users=[{"name": user["name"], "capacity": "editor"}])
    dataset = factories.Dataset(owner_org=org["id"], title="Badplatser", notes="Kort.")
    return user, dataset


def _context(user):
    return {"user": user["name"], "model": ckan_model, "session": ckan_model.Session}


def _start(user, dataset, **extra):
    return jobs.metadata_assistant_job_start(_context(user), dict({"kind": "review", "id": dataset["id"]}, **extra))


def test_without_a_worker_the_request_runs_at_once_and_is_remembered(provider):
    user, dataset = _editor_and_dataset()
    first = _start(user, dataset)
    assert first["state"] == "done" and not first["cached"]
    assert first["result"]["summary"] == "Review 1 of Badplatser"
    second = _start(user, dataset)
    assert second["cached"] and second["prepared_at"] and provider.reviews == 1
    fresh = _start(user, dataset, fresh=True)
    assert not fresh["cached"] and provider.reviews == 2


def test_an_edit_of_the_text_is_a_miss(provider):
    user, dataset = _editor_and_dataset()
    _start(user, dataset)
    toolkit.get_action("package_patch")(_context(user), {"id": dataset["id"], "notes": "Ny text om badplatser."})
    assert not _start(user, dataset)["cached"]
    assert provider.reviews == 2


def test_cache_only_answers_from_the_cache_or_says_none(provider):
    user, dataset = _editor_and_dataset()
    assert _start(user, dataset, cache_only=True) == {"state": "none"}
    assert provider.reviews == 0
    _start(user, dataset)
    assert _start(user, dataset, cache_only=True)["cached"]


def test_only_the_latest_review_of_a_dataset_is_kept(provider):
    user, dataset = _editor_and_dataset()
    _start(user, dataset)
    toolkit.get_action("package_patch")(_context(user), {"id": dataset["id"], "notes": "Ny text om badplatser."})
    _start(user, dataset)
    assert ckan_model.Session.query(ReviewCache).filter_by(package_id=dataset["id"]).count() == 1


def test_a_visitor_and_a_reader_may_not_start_a_request(provider):
    user, dataset = _editor_and_dataset()
    with pytest.raises(toolkit.NotAuthorized):
        jobs.metadata_assistant_job_start({"user": "", "model": ckan_model}, {"kind": "review", "id": dataset["id"]})
    stranger = factories.User()
    with pytest.raises(toolkit.NotAuthorized):
        _start(stranger, dataset)
    assert provider.reviews == 0


def test_a_provider_error_is_an_error_message(provider):
    user, dataset = _editor_and_dataset()
    provider.fail = ProviderError("The AI is tired.")
    with pytest.raises(toolkit.ValidationError) as raised:
        _start(user, dataset)
    assert "The AI is tired." in str(raised.value)


def test_unknown_kind_is_refused(provider):
    user, dataset = _editor_and_dataset()
    with pytest.raises(toolkit.ValidationError):
        jobs.metadata_assistant_job_start(_context(user), {"kind": "nonsense"})
    with pytest.raises(toolkit.ValidationError):   # not a string: refused the same way, not a 500
        jobs.metadata_assistant_job_start(_context(user), {"kind": ["review"]})


def test_each_kind_asks_whether_the_ai_can_be_used_for_its_purpose(provider, monkeypatch):
    asked = []
    monkeypatch.setattr("ckanext.metadata_assistant.ai.problem", lambda *a: asked.append(a) or "Not for this.")
    user, dataset = _editor_and_dataset()
    for kind in ("review", "translate", "landing"):
        with pytest.raises(toolkit.ValidationError):
            jobs.metadata_assistant_job_start(_context(user), {"kind": kind, "id": dataset["id"],
                                                               "url": "https://example.org/d"})
    assert asked == [("review",), ("translate",), ("landing_page",)]


@pytest.mark.ckan_config("ckanext.metadata_assistant.jobs", "on")
def test_through_the_queue_a_worker_answers_and_only_the_owner_may_ask(provider):
    from ckan.lib.jobs import get_queue
    from rq import SimpleWorker

    user, dataset = _editor_and_dataset()
    started = _start(user, dataset)
    assert started["state"] == "queued" and started["job_id"]
    status = jobs.metadata_assistant_job_status(_context(user), {"job_id": started["job_id"]})
    assert status["state"] == "queued"
    assert provider.reviews == 0

    queue = get_queue(jobs.QUEUE)
    SimpleWorker([queue], connection=queue.connection).work(burst=True)

    done = jobs.metadata_assistant_job_status(_context(user), {"job_id": started["job_id"]})
    assert done["state"] == "done" and done["result"]["summary"] == "Review 1 of Badplatser"
    # the answer is also what the next editor gets from the cache
    assert _start(user, dataset)["cached"]
    with pytest.raises(toolkit.NotAuthorized):
        jobs.metadata_assistant_job_status(_context(factories.User()), {"job_id": started["job_id"]})
    sysadmin = factories.Sysadmin()
    assert jobs.metadata_assistant_job_status(_context(sysadmin), {"job_id": started["job_id"]})["state"] == "done"
    redis = limits.connection()
    assert int(redis.get("%sactive:%s" % (limits.KEY, user["name"])) or 0) == 0  # the job's place is given back


@pytest.mark.ckan_config("ckanext.metadata_assistant.jobs", "on")
def test_a_failed_job_says_why_without_a_stack_trace(provider):
    from ckan.lib.jobs import get_queue
    from rq import SimpleWorker

    user, dataset = _editor_and_dataset()
    provider.fail = ProviderError("The AI is tired.")
    started = _start(user, dataset)
    queue = get_queue(jobs.QUEUE)
    SimpleWorker([queue], connection=queue.connection).work(burst=True)
    status = jobs.metadata_assistant_job_status(_context(user), {"job_id": started["job_id"]})
    assert status == {"state": "failed", "error": "The AI is tired."}


@pytest.mark.ckan_config("ckanext.metadata_assistant.jobs", "on")
@pytest.mark.ckan_config("ckanext.metadata_assistant.ai_max_jobs_per_user", "2")
def test_a_user_cannot_have_more_jobs_than_the_quota(provider):
    user, dataset = _editor_and_dataset()
    _start(user, dataset)
    _start(user, dataset)
    with pytest.raises(toolkit.ValidationError) as raised:
        _start(user, dataset)
    assert "2 AI requests" in str(raised.value)


def test_prepared_reviews_are_queued_once_and_skipped_when_current(provider, monkeypatch):
    queued = []
    monkeypatch.setattr(jobs, "enqueue", lambda spec, user, queue_name=jobs.QUEUE, title="": queued.append(
        (queue_name, spec)))
    user, dataset = _editor_and_dataset()
    context = {"user": factories.Sysadmin()["name"], "ignore_auth": True, "model": ckan_model}
    assert jobs.enqueue_prepared_review(context, dataset["id"]) == "queued"
    assert queued[0][0] == jobs.BULK_QUEUE and queued[0][1]["read_landing"]
    jobs.run_job(queued[0][1])
    assert jobs.enqueue_prepared_review(context, dataset["id"]) == "prepared"
    assert len(queued) == 1


def test_a_review_is_not_shared_between_datasets_or_with_and_without_the_page():
    request = {"title": "A", "landing_page_url": "https://example.org/"}
    base = cache.review_digest(request, "m", "d1")
    assert cache.review_digest(request, "m", "d2") != base
    assert cache.review_digest(dict(request, landing_page_extract={"summary": "x"}), "m", "d1") != base
    assert cache.review_digest(dict(request, landing_page_extract={"summary": "y"}), "m", "d1") == \
        cache.review_digest(dict(request, landing_page_extract={"summary": "x"}), "m", "d1")


def test_a_translation_is_tried_again_after_a_rate_limit(monkeypatch):
    class Limited(Exception):
        status_code = 429

    calls = []

    def execute(spec):
        calls.append(1)
        error = ProviderError("limited")
        error.__cause__ = Limited()
        raise toolkit.ValidationError({"ai": ["limited"]}) from error

    monkeypatch.setattr(jobs.actions, "execute_translation", execute)
    monkeypatch.setattr(limits, "retry_pauses", lambda config=None: (0.0, 0.0))
    outcome = jobs.run_job({"kind": "translate"}, "")
    assert outcome["ok"] is False and len(calls) == 3
    calls.clear()
    jobs.run_job({"kind": "translate", "inline": True}, "")
    assert len(calls) == 1  # inside a web request nobody waits for a new try


def test_a_worker_that_stopped_beating_is_not_counted(monkeypatch):
    import datetime
    from types import SimpleNamespace

    now = datetime.datetime.now(datetime.timezone.utc)
    beats = [now - datetime.timedelta(seconds=20), now - datetime.timedelta(minutes=5), None]
    import rq

    monkeypatch.setattr(rq.Worker, "all", classmethod(
        lambda cls, queue=None: [SimpleNamespace(last_heartbeat=b) for b in beats]))
    assert jobs.workers_listening() == 1


def test_the_mode_follows_the_workers_without_a_restart(provider, monkeypatch):
    user, dataset = _editor_and_dataset()
    assert _start(user, dataset, fresh=True)["state"] == "done"      # no worker: in the page
    monkeypatch.setattr(jobs, "workers_listening", lambda queue_name=jobs.QUEUE: 1)
    assert _start(user, dataset, fresh=True)["state"] == "queued"    # a worker appears: queued
    monkeypatch.setattr(jobs, "workers_listening", lambda queue_name=jobs.QUEUE: 0)
    assert _start(user, dataset, fresh=True)["state"] == "done"      # it goes away: in the page again


def test_review_all_does_not_queue_the_same_text_twice(provider, monkeypatch):
    queued = []
    monkeypatch.setattr(jobs, "enqueue", lambda spec, user, queue_name=jobs.QUEUE, title="": queued.append(spec))
    user, dataset = _editor_and_dataset()
    context = {"user": factories.Sysadmin()["name"], "ignore_auth": True, "model": ckan_model}
    assert jobs.enqueue_prepared_review(context, dataset["id"]) == "queued"
    assert jobs.enqueue_prepared_review(context, dataset["id"]) == "waiting"
    assert len(queued) == 1


def test_inside_a_web_request_a_busy_service_is_an_error_not_a_wait(provider):
    user, dataset = _editor_and_dataset()
    redis = limits.connection()
    for n in range(4):
        limits.try_acquire(redis, 4, "taken%d" % n)
    with pytest.raises(toolkit.ValidationError) as raised:
        _start(user, dataset, fresh=True)
    assert "busy" in str(raised.value)
    assert provider.reviews == 0


def test_without_redis_the_review_still_runs(provider, monkeypatch):
    monkeypatch.setattr(limits, "connection", lambda: None)
    user, dataset = _editor_and_dataset()
    assert _start(user, dataset, fresh=True)["state"] == "done"


def test_a_landing_page_read_is_kept_with_the_time_it_was_fetched(provider, monkeypatch):
    reads = []
    monkeypatch.setattr(jobs.actions, "execute_landing_page", lambda spec: reads.append(1) or {"summary": "x"})
    user, dataset = _editor_and_dataset()
    first = jobs.metadata_assistant_job_start(_context(user), {"kind": "landing", "url": "https://example.org/a"})
    assert first["result"]["extract"] == {"summary": "x"} and first["result"]["fetched_at"]
    again = jobs.metadata_assistant_job_start(_context(user), {"kind": "landing", "url": "https://example.org/a"})
    assert again["cached"] and again["result"]["fetched_at"] == first["result"]["fetched_at"] and len(reads) == 1
    fresh = jobs.metadata_assistant_job_start(_context(user), {"kind": "landing", "url": "https://example.org/a", "fresh": True})
    assert not fresh["cached"] and len(reads) == 2


def test_the_completeness_findings_go_to_the_ai_as_codes(provider):
    seen = []
    original = provider.review

    def review(request):
        seen.append(list(request.rule_findings))
        return original(request)

    provider.review = review
    user, dataset = _editor_and_dataset()   # a one-word description
    _start(user, dataset, fresh=True)
    assert "description_too_short (notes)" in seen[0]
    assert all("(" in item and " " in item for item in seen[0])  # code (field): no language, no sentence


def test_the_help_page_is_served_in_both_languages(app):
    for lang in ("en", "sv"):
        response = app.get("/%s/metadata-assistant/help" % lang)
        assert response.status_code == 200
        assert ("Så fungerar metadataassistenten" if lang == "sv" else "How the metadata assistant works") in response.get_data(as_text=True)
