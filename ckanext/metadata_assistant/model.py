"""Stored translation proposals (2026-10-06).

A proposal is the AI's suggested translation of one dataset's title, description and keywords,
kept until an editor has read it and applied or rejected it. Nothing here is metadata: a proposal
changes a dataset only when someone applies it (see ``proposals.apply``).
"""

import uuid
from datetime import datetime, timezone

from ckan.plugins import toolkit
from sqlalchemy import Column, DateTime, String, Text

PENDING, APPLIED, REJECTED, STALE = "pending", "applied", "rejected", "stale"


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TranslationProposal(toolkit.BaseModel):
    __tablename__ = "metadata_assistant_translation_proposal"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    package_id = Column(String(36), nullable=False, index=True)
    status = Column(String(12), nullable=False, default=PENDING, index=True)
    # A digest of the source texts the proposal was made from (title, description, keywords). An
    # edit of the source after that makes the proposal stale: it is not applied.
    source_digest = Column(String(64), nullable=False)
    # The suggestions exactly as metadata_assistant_translate_dataset returned them (JSON).
    suggestions = Column(Text, nullable=False)
    created = Column(DateTime, nullable=False, default=_now)
    decided = Column(DateTime, nullable=True)
    decided_by = Column(String(100), nullable=True)


class ReviewCache(toolkit.BaseModel):
    """The latest AI review of a dataset, kept so it is paid for once (see ``cache``).

    The key is a digest of everything the AI was given (the texts, the guidelines, the instruction, the
    model), so an edit of any of them is a miss. Only the latest review per dataset is kept.
    """

    __tablename__ = "metadata_assistant_review_cache"

    digest = Column(String(64), primary_key=True)
    package_id = Column(String(36), nullable=False, index=True)
    result = Column(Text, nullable=False)
    created = Column(DateTime, nullable=False, default=_now)
