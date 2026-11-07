"""Technical validation and dry-run preview for *candidate* import JSON.

This module does not persist policy data, approve rules, resolve semantic
overlaps, or make a candidate usable for tax calculation. DEC-011 and the
BE2-05/07 models must be completed before those operations exist.
"""

import hashlib
import json
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CandidateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceReference(CandidateModel):
    source_id: UUID
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PolicyRuleCandidate(CandidateModel):
    source_reference: SourceReference
    rule_code: str = Field(min_length=1, max_length=100)
    rule_version: str = Field(min_length=1, max_length=100)
    region_code: str = Field(min_length=1, max_length=100)
    entity_type: str = Field(min_length=1, max_length=100)
    taxpayer_identity: str | None
    filing_type: str = Field(min_length=1, max_length=100)
    period_start: date
    period_end: date | None
    effective_from: date
    effective_to: date | None
    review_status: Literal["candidate"]
    parameters: dict[str, str]
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("rule_code", "rule_version", "region_code", "entity_type", "filing_type")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identifier must not be blank")
        return value

    @model_validator(mode="after")
    def valid_dates(self):
        if self.period_end is not None and self.period_end < self.period_start:
            raise ValueError("period_end precedes period_start")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to precedes effective_from")
        return self


class TemplateField(CandidateModel):
    value_type: Literal["integer_cents", "decimal_string", "date", "text"]
    required: bool


class FormTemplateCandidate(CandidateModel):
    template_id: str = Field(min_length=1, max_length=100)
    template_version: str = Field(min_length=1, max_length=100)
    filing_type: str = Field(min_length=1, max_length=100)
    region_code: str = Field(min_length=1, max_length=100)
    applicable_entity_types: list[str] = Field(min_length=1)
    applicable_taxpayer_identities: list[str]
    effective_from: date
    effective_to: date | None
    fields: dict[str, TemplateField] = Field(min_length=1)
    validation_rules: list[dict[str, str]]
    source_reference: SourceReference
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_status: Literal["candidate"]

    @field_validator("template_id", "template_version", "filing_type", "region_code")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identifier must not be blank")
        return value

    @model_validator(mode="after")
    def valid_dates_and_fields(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to precedes effective_from")
        if any(not name.strip() for name in self.fields):
            raise ValueError("field names must not be blank")
        if any(not value.strip() for value in self.applicable_entity_types):
            raise ValueError("entity types must not be blank")
        return self


class ImportPreview(CandidateModel):
    outcome: Literal["new", "duplicate", "version_conflict"]
    identity: tuple[str, ...]
    content_hash: str
    source_id: str


def canonical_hash(candidate: PolicyRuleCandidate | FormTemplateCandidate) -> str:
    """Hash the parsed candidate without its declared content_hash field."""
    canonical = json.dumps(
        candidate.model_dump(mode="json", exclude={"content_hash"}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _verify(candidate: PolicyRuleCandidate | FormTemplateCandidate, known_sources: dict[str, str]) -> None:
    if candidate.content_hash != canonical_hash(candidate):
        raise ValueError("content_hash_mismatch")
    source = candidate.source_reference
    known_hash = known_sources.get(str(source.source_id))
    if known_hash is None:
        raise ValueError("source_not_found")
    if known_hash != source.content_hash:
        raise ValueError("source_version_conflict")


def _outcome(identity: tuple[str, ...], content_hash: str, existing: dict[tuple[str, ...], str]) -> str:
    previous = existing.get(identity)
    if previous is None:
        return "new"
    return "duplicate" if previous == content_hash else "version_conflict"


def preview_policy_rule(
    raw_json: str | bytes,
    *,
    known_sources: dict[str, str],
    existing: dict[tuple[str, ...], str],
) -> ImportPreview:
    candidate = PolicyRuleCandidate.model_validate_json(raw_json)
    _verify(candidate, known_sources)
    identity = (str(candidate.source_reference.source_id), candidate.rule_code, candidate.rule_version)
    return ImportPreview(
        outcome=_outcome(identity, candidate.content_hash, existing),
        identity=identity,
        content_hash=candidate.content_hash,
        source_id=str(candidate.source_reference.source_id),
    )


def preview_form_template(
    raw_json: str | bytes,
    *,
    known_sources: dict[str, str],
    existing: dict[tuple[str, ...], str],
) -> ImportPreview:
    candidate = FormTemplateCandidate.model_validate_json(raw_json)
    _verify(candidate, known_sources)
    identity = (candidate.template_id, candidate.template_version)
    return ImportPreview(
        outcome=_outcome(identity, candidate.content_hash, existing),
        identity=identity,
        content_hash=candidate.content_hash,
        source_id=str(candidate.source_reference.source_id),
    )
