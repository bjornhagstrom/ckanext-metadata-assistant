"""Command line: ``ckan -c $CKAN_INI metadata-assistant propose-translations`` (2026-10-06)."""

import time

import click
from ckan.plugins import toolkit

from ckanext.metadata_assistant import proposals
from ckanext.metadata_assistant.llm import ProviderError
from ckanext.metadata_assistant.profiles import get_active_profile


@click.group("metadata-assistant", short_help="Metadata assistant commands.")
def metadata_assistant():
    pass


@metadata_assistant.command(
    "propose-translations",
    short_help="Ask the AI for translation proposals for datasets that lack one.")
@click.option("--limit", default=20, show_default=True,
              help="At most this many datasets (one AI request per language for each).")
@click.option("--organization", default="", help="Only this organization (name or id).")
@click.option("--include-outdated", is_flag=True,
              help="Also datasets whose translation is older than the source text.")
@click.option("--dry-run", is_flag=True,
              help="List the datasets and ask the AI for nothing.")
@click.option("--pause", default=1.0, show_default=True, help="Seconds between AI requests.")
def propose_translations(limit, organization, include_outdated, dry_run, pause):
    """Store suggested translations as proposals. Nothing is saved to the datasets: an editor
    reads each proposal at /metadata-assistant/translations and applies or rejects it. Every
    request is a paid AI call, so run it deliberately and start with a small --limit."""
    user = toolkit.get_action("get_site_user")({"ignore_auth": True}, {})["name"]
    context = {"user": user, "ignore_auth": True}
    profile = get_active_profile()
    if not profile.translation_targets or not profile.target_languages:
        raise click.ClickException("The active profile has no fields for translation.")
    found = stored = failed = 0
    for dataset in proposals.candidates(context, profile, organization, include_outdated):
        if found >= limit:
            click.echo("Stopped at --limit %d; run again for more." % limit)
            break
        found += 1
        title = dataset.get("title") or dataset["name"]
        if dry_run:
            click.echo("would propose: %s (%s)" % (dataset["name"], title))
            continue
        try:
            item = proposals.propose(context, dataset, profile)
        except (toolkit.ValidationError, ProviderError) as error:
            failed += 1
            click.echo("FAILED %s: %s" % (dataset["name"], error))
            continue
        if item is None:
            click.echo("nothing to suggest: %s" % dataset["name"])
        else:
            stored += 1
            click.echo("proposed: %s" % dataset["name"])
        time.sleep(max(0.0, pause))
    if dry_run:
        click.echo("%d dataset(s) would get a proposal." % found)
    else:
        click.echo("%d proposal(s) stored, %d failed. Review them at %s/metadata-assistant/translations"
                   % (stored, failed, toolkit.config.get("ckan.site_url", "").rstrip("/")))


@metadata_assistant.command(
    "worker", short_help="Run a worker that does the AI requests waiting in the queues.")
@click.option("--burst", is_flag=True, help="Stop when the queues are empty.")
def worker(burst):
    """Run the AI requests that editors (queue 'metadata_assistant') and ``review-all`` (queue
    'metadata_assistant_bulk') have queued. Editors' requests come first. Start as many as the AI service
    allows at a time; ``ai_max_concurrent`` keeps them all within that."""
    from ckan.lib.jobs import Worker

    from ckanext.metadata_assistant import jobs

    # A short worker time to live: a worker that dies without saying so (a crash) is forgotten after a minute
    # instead of seven, and until then the page would queue requests nobody is going to run.
    Worker([jobs.QUEUE, jobs.BULK_QUEUE], worker_ttl=60).work(burst=burst)


@metadata_assistant.command(
    "review-all", short_help="Queue AI reviews to have suggestions ready when an editor opens a dataset.")
@click.option("--limit", default=0, show_default=True, help="At most this many datasets (0 = all).")
@click.option("--organization", default="", help="Only this organization (name or id).")
@click.option("--dry-run", is_flag=True, help="Count the datasets, queue nothing.")
def review_all(limit, organization, dry_run):
    """Queue a review for every dataset that has none ready for its current text. The reviews are
    made by the workers (``worker``), the landing page is read where the dataset has one, and the result
    is kept until the text changes. Nothing is saved to a dataset: an editor reads the suggestions and
    applies the ones they want. Every review is a paid AI call; start with a small --limit."""
    from ckanext.metadata_assistant import cache, jobs

    user = toolkit.get_action("get_site_user")({"ignore_auth": True}, {})["name"]
    context = {"user": user, "ignore_auth": True}
    fq = ""
    if organization:
        fq = "+owner_org:%s" % toolkit.get_action("organization_show")(dict(context), {"id": organization})["id"]
    queued = prepared = start = 0
    while True:
        page = toolkit.get_action("package_search")(dict(context), {
            "fq": fq, "rows": 200, "start": start, "include_private": True, "sort": "name asc"})
        for dataset in page["results"]:
            if limit and queued >= limit:
                break
            if dry_run:
                spec = jobs.prepare(dict(context), {"kind": "review", "id": dataset["id"]})
                outcome = "prepared" if cache.review_get(spec["digest"]) else "queued"
            else:
                outcome = jobs.enqueue_prepared_review(dict(context), dataset["id"])
            if outcome in ("prepared", "waiting"):
                prepared += 1
            else:
                queued += 1
        start += 200
        if (limit and queued >= limit) or start >= page["count"]:
            break
    click.echo("%s %d review(s), %d already up to date or waiting in the queue." % ("Would queue" if dry_run else "Queued", queued, prepared))
    if not dry_run and queued and not jobs.workers_listening(jobs.BULK_QUEUE):
        click.echo("No worker is running yet: start one with 'ckan metadata-assistant worker'.")


@metadata_assistant.command("queue", short_help="Show the AI queues, workers, limits and prepared reviews.")
def queue_status():
    from ckan.lib.jobs import get_queue

    from ckanext.metadata_assistant import cache, jobs, limits

    for name in (jobs.QUEUE, jobs.BULK_QUEUE):
        click.echo("%-26s %d waiting, %d worker(s)" % (name, len(get_queue(name)), jobs.workers_listening(name)))
    redis = limits.connection()
    if redis is not None:
        click.echo("calls in progress: %d of %s" % (limits.in_use(redis), limits.setting("ai_max_concurrent") or "unlimited"))
        open_for = limits.breaker_open_for(redis)
        click.echo("limits reached today: %s" % (limits.hits_today(redis) or "none"))
        click.echo("breaker: %s" % ("open for %d s" % open_for if open_for else "closed"))
    click.echo("prepared reviews: %d" % cache.prepared_count())
    click.echo("mode: %s" % jobs.mode())


@metadata_assistant.command(
    "migrate-multilingual",
    short_help="Copy existing titles and descriptions into the multilingual fields.")
@click.option("--dry-run", is_flag=True, help="Show what would change, change nothing.")
def migrate_multilingual(dry_run):
    """After adding title_translated and notes_translated to the schema: fill them from the existing text."""
    from ckanext.metadata_assistant import multilingual

    count = multilingual.migrate(dry_run=dry_run, echo=click.echo)
    click.echo("%s %d dataset(s)." % ("Dry run:" if dry_run else "Updated and reindexed", count))


@metadata_assistant.command(
    "doctor", short_help="Check what the assistant needs and say what is missing.")
def doctor():
    """List the setup checks (database, AI model and key, metadata schema, languages)."""
    from ckanext.metadata_assistant import checks

    marks = {checks.OK: "ok     ", checks.WARN: "warning", checks.ERROR: "ERROR  "}
    failed = False
    for check in checks.run_checks():
        click.echo("%s %s: %s" % (marks[check["status"]], check["title"], check["detail"]))
        if check["fix"]:
            click.echo("        -> %s" % check["fix"])
        failed = failed or check["status"] == checks.ERROR
    if failed:
        raise click.exceptions.Exit(1)


@metadata_assistant.command(
    "migrate-ai-settings",
    short_help="Move this extension's old AI connection settings and keys to ckanext-ai-connector.")
@click.option("--dry-run", is_flag=True, help="Say what would be done, and change nothing.")
@click.option("--remove-old", is_flag=True,
              help="Only delete the old rows, after the settings were moved by a run without this option.")
def migrate_ai_settings(dry_run, remove_old):
    """Copy the AI settings saved in the interface under ckanext.metadata_assistant.ai_* to ckanext.ai_connector.*, where
    nothing is saved under the new name yet, and re-encrypt the keys entered on the page under ckanext-ai-connector's cipher.
    The copy is made once: a later run copies nothing again, so a key removed or a value reset on the AI settings page never
    comes back. Then run it with --remove-old to delete the old rows. Prints names only, never a value or a key. Options in
    the server's configuration (.env) are not moved: the command lists those still set under the old names."""
    from ckanext.metadata_assistant import migrate_ai

    try:
        if remove_old:
            if not migrate_ai.remove_old(dry_run=dry_run, echo=click.echo):
                click.echo("Nothing to remove.")
        else:
            earlier = migrate_ai.moved()
            if not migrate_ai.migrate(dry_run=dry_run, echo=click.echo) and earlier is None:
                click.echo("Nothing to copy.")
    except RuntimeError as error:
        raise click.ClickException(str(error))
    server = [name for name in migrate_ai.leftovers() if name.startswith("CKANEXT__")]
    for name in server:
        new = migrate_ai.SERVER_RENAMES.get(name.replace("CKANEXT__METADATA_ASSISTANT__", "").lower())
        click.echo("in the server's configuration: rename %s to %s" % (
            name, migrate_ai.env_name(migrate_ai.NEW + new) if new else "nothing (no longer an option; remove it)"))


def get_commands():
    return [metadata_assistant]
