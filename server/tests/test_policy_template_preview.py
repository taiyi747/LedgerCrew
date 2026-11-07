"""Synthetic-only tests for non-persistent policy/template import previews."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.policy_template_preview import (
    FormTemplateCandidate,
    PolicyRuleCandidate,
    canonical_hash,
    preview_form_template,
    preview_policy_rule,
)

SOURCE_ID = "00000000-0000-4000-8000-000000000901"
SOURCE_HASH = "a" * 64
KNOWN_SOURCES = {SOURCE_ID: SOURCE_HASH}


def policy_payload() -> dict:
    return {
        "source_reference": {"source_id": SOURCE_ID, "content_hash": SOURCE_HASH},
        "rule_code": "SYNTHETIC_RULE",
        "rule_version": "synthetic-v1",
        "region_code": "SYNTHETIC_REGION",
        "entity_type": "SYNTHETIC_ENTITY",
        "taxpayer_identity": None,
        "filing_type": "SYNTHETIC_FILING",
        "period_start": "2026-01-01",
        "period_end": "2026-12-31",
        "effective_from": "2026-01-01",
        "effective_to": None,
        "review_status": "candidate",
        "parameters": {"synthetic_key": "example_only"},
    }


def template_payload() -> dict:
    return {
        "template_id": "SYNTHETIC_TEMPLATE",
        "template_version": "synthetic-v1",
        "filing_type": "SYNTHETIC_FILING",
        "region_code": "SYNTHETIC_REGION",
        "applicable_entity_types": ["SYNTHETIC_ENTITY"],
        "applicable_taxpayer_identities": [],
        "effective_from": "2026-01-01",
        "effective_to": None,
        "fields": {"SYNTHETIC_FIELD": {"value_type": "text", "required": True}},
        "validation_rules": [],
        "source_reference": {"source_id": SOURCE_ID, "content_hash": SOURCE_HASH},
        "review_status": "candidate",
    }


def encoded_with_hash(model_type, payload: dict) -> str:
    candidate = model_type.model_validate_json(json.dumps({**payload, "content_hash": "0" * 64}))
    return json.dumps({**payload, "content_hash": canonical_hash(candidate)}, ensure_ascii=False)


def test_new_policy_and_template_are_previewed_without_writes() -> None:
    existing: dict[tuple[str, ...], str] = {}
    policy = preview_policy_rule(
        encoded_with_hash(PolicyRuleCandidate, policy_payload()), known_sources=KNOWN_SOURCES, existing=existing,
    )
    template = preview_form_template(
        encoded_with_hash(FormTemplateCandidate, template_payload()), known_sources=KNOWN_SOURCES, existing=existing,
    )
    assert policy.outcome == template.outcome == "new"
    assert policy.identity == (SOURCE_ID, "SYNTHETIC_RULE", "synthetic-v1")
    assert template.identity == ("SYNTHETIC_TEMPLATE", "synthetic-v1")
    assert existing == {}


def test_documented_synthetic_json_examples_are_valid() -> None:
    examples = Path(__file__).parents[2] / "contracts" / "examples"
    policy = preview_policy_rule(
        (examples / "synthetic_policy_rule_import.json").read_bytes(),
        known_sources=KNOWN_SOURCES,
        existing={},
    )
    template = preview_form_template(
        (examples / "synthetic_form_template_import.json").read_bytes(),
        known_sources=KNOWN_SOURCES,
        existing={},
    )
    assert policy.outcome == template.outcome == "new"


@pytest.mark.parametrize(
    ("model_type", "payload_factory", "preview"),
    [
        (PolicyRuleCandidate, policy_payload, preview_policy_rule),
        (FormTemplateCandidate, template_payload, preview_form_template),
    ],
)
def test_repeated_preview_detects_duplicate_and_same_version_content_conflict(
    model_type, payload_factory, preview,
) -> None:
    original = encoded_with_hash(model_type, payload_factory())
    first = preview(original, known_sources=KNOWN_SOURCES, existing={})
    existing = {first.identity: first.content_hash}
    assert preview(original, known_sources=KNOWN_SOURCES, existing=existing).outcome == "duplicate"
    assert preview(original, known_sources=KNOWN_SOURCES, existing=existing).outcome == "duplicate"
    reordered_json = json.dumps(dict(reversed(list(json.loads(original).items()))), indent=2)
    assert preview(reordered_json, known_sources=KNOWN_SOURCES, existing=existing).outcome == "duplicate"

    changed = payload_factory()
    if model_type is PolicyRuleCandidate:
        changed["parameters"] = {"synthetic_key": "changed_example"}
    else:
        changed["fields"]["SYNTHETIC_FIELD"]["required"] = False
    conflict = preview(encoded_with_hash(model_type, changed), known_sources=KNOWN_SOURCES, existing=existing)
    assert conflict.outcome == "version_conflict"
    assert existing == {first.identity: first.content_hash}


@pytest.mark.parametrize(
    ("model_type", "payload_factory", "preview"),
    [
        (PolicyRuleCandidate, policy_payload, preview_policy_rule),
        (FormTemplateCandidate, template_payload, preview_form_template),
    ],
)
def test_source_must_exist_and_match_pinned_hash(model_type, payload_factory, preview) -> None:
    raw = encoded_with_hash(model_type, payload_factory())
    with pytest.raises(ValueError, match="source_not_found"):
        preview(raw, known_sources={}, existing={})
    with pytest.raises(ValueError, match="source_version_conflict"):
        preview(raw, known_sources={SOURCE_ID: "b" * 64}, existing={})


@pytest.mark.parametrize(
    ("model_type", "payload_factory", "preview"),
    [
        (PolicyRuleCandidate, policy_payload, preview_policy_rule),
        (FormTemplateCandidate, template_payload, preview_form_template),
    ],
)
def test_import_cannot_claim_approval_and_bad_hash_is_rejected(model_type, payload_factory, preview) -> None:
    approved = payload_factory()
    approved["review_status"] = "approved"
    with pytest.raises(ValidationError):
        preview(json.dumps({**approved, "content_hash": "0" * 64}), known_sources=KNOWN_SOURCES, existing={})
    tampered = json.loads(encoded_with_hash(model_type, payload_factory()))
    tampered["content_hash"] = "f" * 64
    with pytest.raises(ValueError, match="content_hash_mismatch"):
        preview(json.dumps(tampered), known_sources=KNOWN_SOURCES, existing={})


def test_missing_metadata_invalid_version_dates_and_template_field_type() -> None:
    missing = policy_payload()
    del missing["region_code"]
    with pytest.raises(ValidationError):
        PolicyRuleCandidate.model_validate_json(json.dumps({**missing, "content_hash": "0" * 64}))
    invalid_version = policy_payload()
    invalid_version["rule_version"] = "  "
    with pytest.raises(ValidationError):
        PolicyRuleCandidate.model_validate_json(json.dumps({**invalid_version, "content_hash": "0" * 64}))
    invalid_dates = policy_payload()
    invalid_dates["effective_to"] = "2025-12-31"
    with pytest.raises(ValidationError):
        PolicyRuleCandidate.model_validate_json(json.dumps({**invalid_dates, "content_hash": "0" * 64}))
    invalid_field = template_payload()
    invalid_field["fields"]["SYNTHETIC_FIELD"]["value_type"] = "unknown"
    with pytest.raises(ValidationError):
        FormTemplateCandidate.model_validate_json(json.dumps({**invalid_field, "content_hash": "0" * 64}))
