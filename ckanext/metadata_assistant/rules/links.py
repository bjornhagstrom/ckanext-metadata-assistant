"""Slips in the addresses of a dataset that can be seen without asking the network.

Deterministic, like the rest of the rule engine: they only look at the text of each address and point the editor to it. Whether a link
works is a question for the link check (see ``link_results.py``), not for these rules.
"""

from __future__ import annotations

import json
import re
from typing import List, Mapping
from urllib.parse import urlsplit

from ckanext.metadata_assistant.localization import _
from ckanext.metadata_assistant.rules.profile import RuleProfile

DATASET_LINK_FIELDS = ("url", "conforms_to", "documentation")
RESOURCE_LINK_FIELDS = ("url", "access_url", "download_url", "conforms_to", "documentation")
# Specification links are often namespace identifiers that start with http:// for good reasons; they are not asked to be https.
_NO_HTTPS_HINT = ("conforms_to",)


def addresses(value: object) -> List[str]:
    """The addresses in a field: a string, a list, or a JSON list in a string."""
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            value = json.loads(value)
        except ValueError:
            pass
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if v and str(v).strip()]
    return [value.strip()] if isinstance(value, str) and value.strip() else []


def _name(resource: Mapping[str, object]) -> str:
    name = resource.get("name")
    if not name and isinstance(resource.get("name_translated"), Mapping):
        translated = resource["name_translated"]
        from ckanext.metadata_assistant.localization import pick_language

        name = pick_language(dict(translated))
    return str(name or resource.get("url") or "")


def _scheme(address: str) -> str:
    try:
        return urlsplit(address).scheme
    except ValueError:
        return ""


def _problems(field: str, address: str):
    """The slips in one address: ``(code, severity, message-template)`` tuples."""
    found = []
    if re.search(r"\s", address):
        found.append(("link_has_spaces", "warning",
                      _("The address '{address}' has a space in it. Addresses cannot contain spaces: remove it.")))
    elif "://" not in address and not address.startswith(("mailto:", "urn:", "tel:")) and (
            address.lower().startswith("www.") or re.match(r"^[\w-]+(\.[\w-]+)+(/|$)", address)):
        found.append(("link_without_scheme", "warning",
                      _("The address '{address}' does not start with http:// or https://. Without it the link does not work.")))
    elif _scheme(address) == "http" and field not in _NO_HTTPS_HINT:
        found.append(("link_not_secure", "info",
                      _("The address '{address}' starts with http://. If the site supports https, use that instead.")))
    return found


def check_links(dataset: Mapping[str, object], profile: RuleProfile):
    """Spaces, a missing http(s):// and plain http:// in the dataset's and the resources' addresses."""
    from ckanext.metadata_assistant.rules.engine import Finding

    findings = []
    places = [("", dataset, DATASET_LINK_FIELDS)] + [
        (_name(r), r, RESOURCE_LINK_FIELDS) for r in dataset.get("resources") or [] if isinstance(r, Mapping)]
    for resource_name, holder, fields in places:
        for field in fields:
            if field == "url" and holder.get("url_type") == "upload":
                continue
            for address in addresses(holder.get(field)):
                for code, severity, template in _problems(field, address):
                    message = template.format(address=address)
                    if resource_name:
                        message += " " + _("(In the distribution '{name}'.)").format(name=resource_name)
                    findings.append(Finding(field=field if not resource_name else "", severity=severity, code=code,
                                            message=message, source=profile.name))
    return findings
