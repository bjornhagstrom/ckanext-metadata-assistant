"""Distributions that look like an API but have no data service (DIGG recommendation 6).

A distribution that is an API, that is, something one sends requests to and gets data back from, should
be described as a data service (``dcat:DataService``) in the DCAT export. Editors often add only a
distribution with the API address. These checks are deterministic: they look at the address, the format and
the specification links, and only point the editor to the right place. They never change anything.
"""

from __future__ import annotations

import json
import re
from typing import List, Mapping
from urllib.parse import parse_qs, urlsplit

from ckanext.metadata_assistant.localization import _
from ckanext.metadata_assistant.rules.profile import RuleProfile

_API_FORMATS = {"WMS", "WFS", "WMTS", "WCS", "CSW", "SOS", "ODATA", "API", "REST", "GRAPHQL", "SPARQL"}
_API_PATH = re.compile(
    r"(^|/)(api|rest|wfs|wms|wmts|wcs|ows|csw|odata|graphql|sparql|geoserver)(/|$)"
    r"|/arcgis/rest/services|/mapserver(/|$)|/featureserver(/|$)", re.IGNORECASE)
_API_SERVICES = {"wms", "wfs", "wmts", "wcs", "csw", "sos"}
_SPEC_WORDS = ("openapi", "swagger")
_FILE_EXTENSIONS = {"csv", "tsv", "xls", "xlsx", "ods", "zip", "gz", "7z", "pdf", "gpkg", "shp", "geojson",
                    "txt", "parquet", "kml", "kmz", "gml"}


def _extension(url: str) -> str:
    path = urlsplit(url).path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[-1].lower() if "." in path else ""


def _texts(value: object) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [t for v in value for t in _texts(v)]
    return []


def looks_like_file(url: str) -> bool:
    return _extension(url) in _FILE_EXTENSIONS


def looks_like_api(resource: Mapping[str, object]) -> bool:
    """True when the distribution's address, format or specification links say it is an API."""
    url = str(resource.get("url") or "").strip()
    if (str(resource.get("format") or "").strip().upper() in _API_FORMATS):
        return True
    if any(word in text.lower() for text in _texts(resource.get("conforms_to")) for word in _SPEC_WORDS):
        return True
    if not url or looks_like_file(url):
        return False
    parts = urlsplit(url)
    query = {k.lower(): [v.lower() for v in vs] for k, vs in parse_qs(parts.query).items()}
    if any(v in _API_SERVICES for v in query.get("service", [])) or "getcapabilities" in query.get("request", []):
        return True
    return bool(_API_PATH.search(parts.path))


_REGISTRY_FIELD = "access_service_ids"   # ckanext-data-service-registry: services kept once and chosen by id


def _registry_services(resource: Mapping[str, object]) -> list:
    """The services a distribution points at in the data service registry, if it has any. The registry is optional: without it (or outside
    CKAN) each id still counts as a service, with nothing known about its contact, so that the distribution is not said to lack one."""
    value = resource.get(_REGISTRY_FIELD)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = [part.strip() for part in value.split(",")]
    ids = [str(v).strip() for v in value or [] if str(v).strip()] if isinstance(value, (list, tuple)) else []
    found = []
    for service_id in ids:
        service = {"registry_service": service_id}
        try:
            import ckan.plugins as plugins
            if plugins.plugin_loaded("data_service_registry"):
                from ckanext.data_service_registry import model as registry
                item = registry.get(service_id)
                if item is not None:
                    service = dict(item.as_dict(), registry_service=service_id)
        except Exception:   # outside CKAN, or the registry is not usable
            pass
        found.append(service)
    return found


def _services(resource: Mapping[str, object], field: str) -> list:
    value = resource.get(field)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = []
    embedded = [v for v in value or [] if isinstance(v, Mapping) and any(v.values())]
    return embedded + _registry_services(resource)


def _name(resource: Mapping[str, object]) -> str:
    name = resource.get("name")
    if not name and isinstance(resource.get("name_translated"), Mapping):
        translated = resource["name_translated"]
        from ckanext.metadata_assistant.localization import pick_language

        name = pick_language(dict(translated))
    return str(name or resource.get("url") or "")


_DATASET_CONTACT_FIELDS = ("contact_point_ids", "contact", "contact_uri", "contact_email", "contact_name", "maintainer_email",
                           "maintainer", "author_email", "author")
_EMAIL = re.compile(r"[^@\s<>\"{}|\\^`]+@[^@\s<>\"{}|\\^`]+")


def _own_contact(service: Mapping[str, object]) -> bool:
    email = str(service.get("contact_email") or "").strip()
    return bool(_EMAIL.fullmatch(email[7:] if email.lower().startswith("mailto:") else email))


def _dataset_has_contact(dataset: Mapping[str, object]) -> bool:
    """A contact point the export will carry from the dataset: the actor registry's, or CKAN's and ckanext-dcat's contact fields."""
    return any(dataset.get(field) for field in _DATASET_CONTACT_FIELDS)


def _actor_registry_installed() -> bool:
    try:
        import ckan.plugins as plugins
        return plugins.plugin_loaded("actor_registry")
    except Exception:   # outside CKAN (unit tests)
        return False


def check_hvd_service_contact(dataset: Mapping[str, object], profile: RuleProfile):
    """A high-value dataset with a data service needs a contact point for the service (DCAT-AP HVD 3.0.1 SHACL: an error).
    Nothing is said about a dataset without a data service. The actor registry is a tip, not a requirement: named whether or not it is installed."""
    from ckanext.metadata_assistant.rules.engine import Finding

    field = profile.service_field
    if not field or not dataset.get("hvd_category"):
        return []
    services = [s for resource in dataset.get("resources") or [] for s in _services(resource, field)]
    # Each service needs one: its own e-mail address, or else the dataset's contact point (which the export copies to every service).
    if not services or _dataset_has_contact(dataset) or all(_own_contact(service) for service in services):
        return []
    message = _("The data service has no contact point. A high-value dataset with an API must have one, so that "
                "users of the API know whom to ask. Add a contact point to the dataset, or an e-mail address to the data service.")
    # A tip either way: installed, choose from it; not installed, it is a good way to keep contact points (the rule works without it).
    if _actor_registry_installed():
        message += " " + _("You can choose a contact point from the actor registry.")
    else:
        message += " " + _("The actor registry extension (ckanext-actor-registry, https://github.com/bjornhagstrom/ckanext-actor-registry) is a good way to keep contact points in one place.")
    return [Finding(field=field, severity="error", code="hvd_service_without_contact", message=message, source=profile.name)]


_HVD_LICENCES = re.compile(
    r"(?:^|/)(?:cc-zero|cc0(?:-1\.0)?|cc-by(?:-4\.0)?|cc_by_4_0)$|creativecommons\.org/publicdomain/zero/|creativecommons\.org/licenses/by/4\.0",
    re.IGNORECASE)


def check_hvd_licence(dataset: Mapping[str, object], profile: RuleProfile):
    """The licence of a high-value dataset must be CC0 or CC BY 4.0 (the DCAT-AP HVD 3.0.1 shapes accept no other, for the dataset's
    distributions and its API). A missing licence is the ordinary licence rule's business."""
    from ckanext.metadata_assistant.rules.engine import Finding

    if not dataset.get("hvd_category"):
        return []
    values = [dataset.get("license_id")] + [r.get("license") for r in dataset.get("resources") or []]
    bad = [str(v).strip() for v in values if str(v or "").strip() and not _HVD_LICENCES.search(str(v).strip())]
    if not bad:
        return []
    return [Finding(
        field="license_id", severity="error", code="hvd_licence",
        message=_("A high-value dataset must be published under CC0 or CC BY 4.0. The licence '{licence}' does not meet the HVD rules.").format(licence=bad[0]),
        source=profile.name)]


def check_data_services(dataset: Mapping[str, object], profile: RuleProfile):
    """An API without a data service, and a data service on what looks like a plain file."""
    from ckanext.metadata_assistant.rules.engine import Finding

    field = profile.service_field
    if not field:
        return []
    findings = []
    for resource in dataset.get("resources") or []:
        services = _services(resource, field)
        if not services and looks_like_api(resource):
            findings.append(Finding(
                field=field, severity="warning", code="api_without_service",
                message=_(
                    "The distribution '{name}' looks like an API but is not described as a data service. "
                    "Add a data service to the distribution so that it is described as a data service."
                ).format(name=_name(resource)),
                source=profile.name))
        elif services and not looks_like_api(resource) and looks_like_file(str(resource.get("url") or "")):
            findings.append(Finding(
                field=field, severity="info", code="service_on_file",
                message=_(
                    "The distribution '{name}' has a data service, but its address looks like a file "
                    "download. A file is not a data service: remove the data service if that is the case."
                ).format(name=_name(resource)),
                source=profile.name))
    return findings
