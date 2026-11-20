"""Deterministic, dependency-free metadata quality rules.

This package has no CKAN or network dependencies on purpose, so it can be
unit tested with a plain ``python3 -m unittest`` run, without Docker or a
running CKAN instance. The AI-assisted review lives elsewhere in the
extension (``ckanext.metadata_assistant.llm``).
"""

from ckanext.metadata_assistant.rules.profile import RuleProfile
from ckanext.metadata_assistant.rules.engine import Finding, review_dataset

__all__ = ["RuleProfile", "Finding", "review_dataset"]
