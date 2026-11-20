"""What the link check has found about the addresses of a saved dataset, as findings in the review.

Only when the link check is installed and the user may see its results; otherwise nothing is added. The results are the ones from the
latest check, so a link the editor has just changed is not in them until it has been checked again.
"""

from __future__ import annotations

from typing import List

from ckan import plugins
from ckan.plugins import toolkit

from ckanext.metadata_assistant.localization import _
from ckanext.metadata_assistant.rules.engine import Finding


def findings_from_link_check(dataset, profile, context) -> List[Finding]:
    package_id = dataset.get("id")
    if not package_id or not plugins.plugin_loaded("link_check"):
        return []
    try:
        shown = toolkit.get_action("link_check_dataset_show")({"user": context.get("user") or ""}, {"id": package_id})
        from ckanext.link_check import logic
    except (toolkit.NotAuthorized, toolkit.ObjectNotFound, ImportError):
        return []
    current = _current_addresses(dataset)
    findings = []
    for result in shown.get("results") or []:
        if result["url"] not in current:
            continue  # changed since that check
        field = result.get("field") or ""
        if result["state"] == "redirect":
            suggestion = logic.suggest(result["url"], result.get("final_url"), result.get("message"))
            if suggestion:
                findings.append(Finding(
                    field=field if not result.get("resource_id") else "", severity="warning", code="link_forwards",
                    message=_("The link check found that the address '{address}' forwards to '{final}'. "
                              "The EU quality check only counts links that answer directly: use the address it forwards to.")
                    .format(address=result["url"], final=suggestion[0]), source=profile.name))
        elif result["state"] in logic.FAILING:
            findings.append(Finding(
                field=field if not result.get("resource_id") else "", severity="warning", code="link_broken",
                message=_("The link check found that the address '{address}' does not work.").format(address=result["url"]),
                source=profile.name))
    return findings


def _current_addresses(dataset) -> set:
    from ckanext.metadata_assistant.rules.links import DATASET_LINK_FIELDS, RESOURCE_LINK_FIELDS, addresses

    found = set()
    for field in DATASET_LINK_FIELDS:
        found.update(addresses(dataset.get(field)))
    for resource in dataset.get("resources") or []:
        for field in RESOURCE_LINK_FIELDS:
            found.update(addresses(resource.get(field)))
    return found


OPTION = "ckanext.metadata_assistant.check_addresses"
MAX_ADDRESSES = 3
BUDGET_SECONDS = 12.0   # all the addresses of one review together; the rest are left for the next review


def live_check_enabled() -> bool:
    """On when the sysadmin has turned it on and the link check is installed."""
    return str(toolkit.config.get(OPTION) or "off").strip().lower() == "on" and plugins.plugin_loaded("link_check")


def live_findings(addresses, profile, context):
    """``[(address, Finding)]``: the answer of the link check for addresses the editor has just typed (at most MAX_ADDRESSES, http and
    https only). A failure to check never fails the review: the address is then simply not remarked on."""
    import logging

    if not addresses or not live_check_enabled():
        return []
    import time

    found = []
    started = time.monotonic()
    for address in [str(a).strip() for a in addresses if a][:MAX_ADDRESSES]:
        if time.monotonic() - started > BUDGET_SECONDS:
            break
        try:
            answer = toolkit.get_action("link_check_check_address")({"user": context.get("user") or ""}, {"url": address})
        except (toolkit.NotAuthorized, toolkit.ValidationError):
            continue
        except Exception as error:  # a network or database slip must not break the review
            logging.getLogger(__name__).warning("Address check failed: %s", type(error).__name__)
            continue
        if answer["state"] == "redirect" and answer.get("suggestion"):
            found.append((address, Finding(
                field="", severity="warning", code="link_forwards_now", source=profile.name,
                message=_("The address '{address}' forwards to '{final}' (checked just now). The EU quality check only counts links "
                          "that answer directly: use the address it forwards to.").format(
                              address=address, final=answer["suggestion"]["address"]),
                suggestion=answer["suggestion"]["address"])))
        elif answer["state"] == "ok" and answer.get("suggestion"):
            found.append((address, Finding(
                field="", severity="info", code="link_use_https_now", source=profile.name,
                message=_("The address '{address}' also answers over https (checked just now). Use that address: it is "
                          "the secure one.").format(address=address),
                suggestion=answer["suggestion"]["address"])))
        elif answer["state"] == "redirect":
            found.append((address, Finding(
                field="", severity="info", code="link_forwards_unclear", source=profile.name,
                message=_("The address '{address}' forwards to '{final}' (checked just now). Check that it is the right page "
                          "before you use it.").format(address=address, final=answer.get("final_url") or ""))))
        elif answer["state"] in ("broken", "error", "timeout"):
            found.append((address, Finding(
                field="", severity="warning", code="link_broken_now", source=profile.name,
                message=_("The address '{address}' did not answer just now. Check that it is spelled right.").format(address=address))))
    return found


def read_page_on_open_enabled() -> bool:
    """Whether the landing page is read in the background when the edit form opens (``read_page_on_open``, on by default since 2026-10-26): the
    reading is then done when the editor asks for suggestions. It costs a model call for every landing page that is not read already."""
    from ckan.plugins import toolkit

    return str(toolkit.config.get("ckanext.metadata_assistant.read_page_on_open") or "on").strip().lower() == "on"
