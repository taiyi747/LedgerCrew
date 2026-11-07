"""BE2-10-11 synthetic-only tests for generic declaration-form field mapping and validation.

Every form fixture in this module is a SYNTHETIC TEST TEMPLATE (``SYNTHETIC_TEST_*`` keys).
It is NOT an official tax form and must never be used for a real filing. With no verified
official template (DEC-011 pending) these tests only cover the generic mechanisms that
exist in the repository today:

* candidate template structure, source pinning and version identity
  (``app.services.policy_template_preview``, dry-run only, no persistence),
* field/amount/date/enum strictness and version pinning of the proposed P2 wire contracts
  (``contracts/schemas.py``, a design artifact with no mounted routes),
* MVP report evidence-reference validation (``app.services.report_service``) as the only
  existing runtime evidence check; the MVP report is NOT a tax return draft.

Tests named ``test_gap_*`` assert today's permissive behaviour to document enforcement
that BE2-07/BE2-08 must add. They record missing checks; they do not mean the requirement
passes, and no result here may be cited as an accepted official filing form.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_stage2 import create_order, exercise
from test_stage6 import make_batch_with_exception

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.session import make_engine
from app.schemas.agent import AgentTaskCreate
from app.services import agent_service, report_service
from app.services.policy_template_preview import (
    FormTemplateCandidate,
    canonical_hash,
    preview_form_template,
)

SOURCE_ID = "00000000-0000-4000-8000-000000000901"
SOURCE_HASH = "a" * 64
KNOWN_SOURCES = {SOURCE_ID: SOURCE_HASH}
CALC_ID = "00000000-0000-4000-8000-0000000000c1"
TASK_ID = "00000000-0000-4000-8000-0000000000f1"
DRAFT_ID = "00000000-0000-4000-8000-0000000000d1"

CONTRACTS_PATH = Path(__file__).parents[2] / "contracts" / "schemas.py"


def _load_p2_contracts():
    """Load the proposed (not mounted) P2 wire contracts as a plain module."""
    spec = importlib.util.spec_from_file_location("p2_contract_schemas", CONTRACTS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


contracts = _load_p2_contracts()


# ---------------------------------------------------------------------------
# Synthetic test-template fixtures (test-only; not official form fields).
# ---------------------------------------------------------------------------

def synthetic_template_v1() -> dict:
    """SYNTHETIC TEST TEMPLATE v1: placeholder fields, no official semantics."""
    return {
        "template_id": "SYNTHETIC_TEST_TEMPLATE",
        "template_version": "synthetic-v1",
        "filing_type": "SYNTHETIC_FILING",
        "region_code": "SYNTHETIC_REGION",
        "applicable_entity_types": ["SYNTHETIC_ENTITY"],
        "applicable_taxpayer_identities": [],
        "effective_from": "2026-01-01",
        "effective_to": None,
        "fields": {
            "SYNTHETIC_TEST_FIELD_TEXT": {"value_type": "text", "required": True},
            "SYNTHETIC_TEST_FIELD_AMOUNT": {"value_type": "integer_cents", "required": True},
            "SYNTHETIC_TEST_FIELD_DATE": {"value_type": "date", "required": False},
            "SYNTHETIC_TEST_FIELD_NOTE": {"value_type": "text", "required": False},
        },
        "validation_rules": [],
        "source_reference": {"source_id": SOURCE_ID, "content_hash": SOURCE_HASH},
        "review_status": "candidate",
    }


def synthetic_template_v2() -> dict:
    """SYNTHETIC TEST TEMPLATE v2: the amount field is mapped under a new key."""
    payload = synthetic_template_v1()
    payload["template_version"] = "synthetic-v2"
    amount = payload["fields"].pop("SYNTHETIC_TEST_FIELD_AMOUNT")
    payload["fields"]["SYNTHETIC_TEST_FIELD_AMOUNT_V2"] = amount
    return payload


def encoded_with_hash(model_type, payload: dict) -> str:
    candidate = model_type.model_validate_json(json.dumps({**payload, "content_hash": "0" * 64}))
    return json.dumps({**payload, "content_hash": canonical_hash(candidate)}, ensure_ascii=False)


def synthetic_evidence(**overrides) -> dict:
    payload = {"kind": "tax_calculation", "id": CALC_ID, "locator": "SYNTHETIC_TEST line 1",
               "content_hash": SOURCE_HASH}
    payload.update(overrides)
    return payload


def synthetic_field_value(**overrides) -> dict:
    payload = {"field_key": "SYNTHETIC_TEST_FIELD_AMOUNT", "value": "1000",
               "evidence": [synthetic_evidence()], "calculation_line_key": "SYNTHETIC_TEST_LINE_AMOUNT"}
    payload.update(overrides)
    return payload


def synthetic_calculation(status: str = "completed", lines: list | None = None,
                          blockers: list | None = None) -> dict:
    return {
        "id": CALC_ID,
        "created_at": "2026-11-07T00:00:00Z",
        "filing_task_id": TASK_ID,
        "status": status,
        "data_version": 1,
        "rule_versions": ["SYNTHETIC_TEST_RULE@synthetic-v1"],
        "form_version": "synthetic-v1",
        "calculation_version": 1,
        "input_hash": SOURCE_HASH,
        "lines": lines if lines is not None else [
            {"key": "SYNTHETIC_TEST_LINE_AMOUNT", "amount_cents": 1000, "ratio": None,
             "formula": "SYNTHETIC_TEST_ONLY", "evidence": [synthetic_evidence()]},
        ],
        "blockers": blockers if blockers is not None else [],
    }


def synthetic_draft(fields: list | None = None, status: str = "draft", missing: list | None = None,
                    blockers: list | None = None, form_version: str = "synthetic-v1") -> dict:
    return {
        "id": DRAFT_ID,
        "created_at": "2026-11-07T00:00:00Z",
        "filing_task_id": TASK_ID,
        "calculation_id": CALC_ID,
        "form_version": form_version,
        "draft_version": 1,
        "data_version": 1,
        "rule_versions": ["SYNTHETIC_TEST_RULE@synthetic-v1"],
        "status": status,
        "fields": fields if fields is not None else [synthetic_field_value()],
        "missing_material_codes": missing if missing is not None else [],
        "blockers": blockers if blockers is not None else [],
        "content_hash": SOURCE_HASH,
        "approved_by": None,
        "approved_at": None,
    }


# ---------------------------------------------------------------------------
# 三、字段测试 (synthetic fixtures; generic mechanisms only).
# ---------------------------------------------------------------------------

def test_s1_required_and_optional_fields_parse_completely() -> None:
    template = FormTemplateCandidate.model_validate_json(
        encoded_with_hash(FormTemplateCandidate, synthetic_template_v1()))
    assert template.fields["SYNTHETIC_TEST_FIELD_AMOUNT"].required is True
    assert template.fields["SYNTHETIC_TEST_FIELD_DATE"].required is False
    draft = contracts.TaxReturnDraftRead.model_validate(synthetic_draft(fields=[
        synthetic_field_value(field_key="SYNTHETIC_TEST_FIELD_TEXT", value="SYNTHETIC", calculation_line_key=None),
        synthetic_field_value(),
        synthetic_field_value(field_key="SYNTHETIC_TEST_FIELD_DATE", value="2026-10-31", calculation_line_key=None),
        synthetic_field_value(field_key="SYNTHETIC_TEST_FIELD_NOTE", value=None, calculation_line_key=None),
    ]))
    assert [item.field_key for item in draft.fields] == [
        "SYNTHETIC_TEST_FIELD_TEXT", "SYNTHETIC_TEST_FIELD_AMOUNT",
        "SYNTHETIC_TEST_FIELD_DATE", "SYNTHETIC_TEST_FIELD_NOTE"]


def test_gap_s2_missing_required_field_is_not_rejected() -> None:
    """GAP: nothing cross-checks draft fields against template ``required`` flags."""
    template = FormTemplateCandidate.model_validate_json(
        encoded_with_hash(FormTemplateCandidate, synthetic_template_v1()))
    assert template.fields["SYNTHETIC_TEST_FIELD_AMOUNT"].required is True
    draft = contracts.TaxReturnDraftRead.model_validate(synthetic_draft(fields=[
        synthetic_field_value(field_key="SYNTHETIC_TEST_FIELD_TEXT", value="SYNTHETIC", calculation_line_key=None),
    ]))
    assert draft.status == "draft"


def test_s3_optional_field_may_be_absent_or_null() -> None:
    draft = contracts.TaxReturnDraftRead.model_validate(synthetic_draft(fields=[
        synthetic_field_value(field_key="SYNTHETIC_TEST_FIELD_NOTE", value=None, calculation_line_key=None),
    ]))
    assert draft.fields[0].value is None
    assert "SYNTHETIC_TEST_FIELD_DATE" not in {item.field_key for item in draft.fields}


def test_s4_field_type_errors_are_rejected() -> None:
    bad_type = synthetic_template_v1()
    bad_type["fields"]["SYNTHETIC_TEST_FIELD_AMOUNT"]["value_type"] = "currency"
    with pytest.raises(ValidationError):
        FormTemplateCandidate.model_validate_json(encoded_with_hash(FormTemplateCandidate, bad_type))
    with pytest.raises(ValidationError):
        contracts.TaxFieldValue.model_validate(synthetic_field_value(value=1000))
    with pytest.raises(ValidationError):
        contracts.TaxFieldValue.model_validate({**synthetic_field_value(), "unexpected_key": "x"})


def test_s5_date_format_errors_are_rejected() -> None:
    bad_format = synthetic_template_v1()
    bad_format["effective_from"] = "2026/01/01"
    with pytest.raises(ValidationError):
        FormTemplateCandidate.model_validate_json(encoded_with_hash(FormTemplateCandidate, bad_format))
    reversed_range = synthetic_template_v1()
    reversed_range["effective_to"] = "2025-12-31"
    with pytest.raises(ValidationError):
        FormTemplateCandidate.model_validate_json(encoded_with_hash(FormTemplateCandidate, reversed_range))
    with pytest.raises(ValidationError):
        contracts.FilingPeriodCreate.model_validate(
            {"period_start": "2026-03-01", "period_end": "2026-02-01", "period_label": "SYNTHETIC"})


def test_gap_s5_date_format_of_field_values_is_not_checked() -> None:
    """GAP: TaxFieldValue.value is an untyped string; invalid dates pass the contract."""
    draft = contracts.TaxReturnDraftRead.model_validate(synthetic_draft(fields=[
        synthetic_field_value(field_key="SYNTHETIC_TEST_FIELD_DATE", value="2026-13-01",
                              calculation_line_key=None),
    ]))
    assert draft.fields[0].value == "2026-13-01"


def test_s6_amount_format_errors_are_rejected() -> None:
    base = {"key": "SYNTHETIC_TEST_LINE_AMOUNT", "ratio": None, "formula": None, "evidence": []}
    with pytest.raises(ValidationError):
        contracts.CalculationLine.model_validate({**base, "amount_cents": "123.45"})
    with pytest.raises(ValidationError):
        contracts.CalculationLine.model_validate({**base, "amount_cents": 12.34})
    with pytest.raises(ValidationError):
        contracts.CalculationLine.model_validate({**base, "amount_cents": 1000, "ratio": "1.2.3"})
    line = contracts.CalculationLine.model_validate({**base, "amount_cents": 1000, "ratio": "0.05"})
    assert line.amount_cents == 1000 and line.ratio == "0.05"


def test_s7_illegal_field_values_are_rejected() -> None:
    self_approved = synthetic_template_v1()
    self_approved["review_status"] = "approved"
    with pytest.raises(ValidationError):
        FormTemplateCandidate.model_validate_json(encoded_with_hash(FormTemplateCandidate, self_approved))
    with pytest.raises(ValidationError):
        contracts.TaxReturnDraftRead.model_validate(synthetic_draft(status="ready"))
    with pytest.raises(ValidationError):
        contracts.EvidenceRef.model_validate(synthetic_evidence(kind="photo"))
    with pytest.raises(ValidationError):
        contracts.TaxCalculationRead.model_validate({**synthetic_calculation(), "status": "finished"})


def test_s8_field_source_must_exist_and_match_pinned_hash() -> None:
    raw = encoded_with_hash(FormTemplateCandidate, synthetic_template_v1())
    with pytest.raises(ValueError, match="source_not_found"):
        preview_form_template(raw, known_sources={}, existing={})
    with pytest.raises(ValueError, match="source_version_conflict"):
        preview_form_template(raw, known_sources={SOURCE_ID: "b" * 64}, existing={})
    tampered = json.loads(raw)
    tampered["content_hash"] = "f" * 64
    with pytest.raises(ValueError, match="content_hash_mismatch"):
        preview_form_template(json.dumps(tampered), known_sources=KNOWN_SOURCES, existing={})


def test_s9_evidence_reference_shape_is_enforced() -> None:
    with pytest.raises(ValidationError):
        contracts.EvidenceRef.model_validate(synthetic_evidence(content_hash="zz" + "a" * 62))
    with pytest.raises(ValidationError):
        contracts.EvidenceRef.model_validate(synthetic_evidence(id="not-a-uuid"))
    with pytest.raises(ValidationError):
        contracts.EvidenceRef.model_validate(synthetic_evidence(kind="photo"))
    ref = contracts.EvidenceRef.model_validate(synthetic_evidence())
    assert ref.kind == "tax_calculation" and ref.locator == "SYNTHETIC_TEST line 1"


def test_s10_draft_requires_pinned_calculation_result() -> None:
    with pytest.raises(ValidationError):
        contracts.TaxReturnDraftCreate.model_validate(
            {"expected_data_version": 1, "form_version": "synthetic-v1"})
    create = contracts.TaxReturnDraftCreate.model_validate(
        {"calculation_id": CALC_ID, "expected_data_version": 1, "form_version": "synthetic-v1"})
    assert str(create.calculation_id) == CALC_ID
    blocked = contracts.TaxCalculationRead.model_validate(synthetic_calculation(
        status="blocked", lines=[], blockers=[
            {"code": "SYNTHETIC_TEST_BLOCKER", "message": "SYNTHETIC_TEST_ONLY", "evidence": []}]))
    assert blocked.status == "blocked" and blocked.lines == [] and blocked.blockers[0].code == "SYNTHETIC_TEST_BLOCKER"


def test_s11_period_range_is_validated() -> None:
    period = contracts.FilingPeriodCreate.model_validate(
        {"period_start": "2026-10-01", "period_end": "2026-10-31", "period_label": "SYNTHETIC"})
    assert period.period_start < period.period_end
    with pytest.raises(ValidationError):
        contracts.FilingPeriodCreate.model_validate(
            {"period_start": "2026-10-01", "period_end": "2026-09-30", "period_label": "SYNTHETIC"})


def test_gap_s11_template_window_is_not_cross_checked_with_filing_period() -> None:
    """GAP: neither the draft contract nor any service links a field/period to the template window."""
    template = FormTemplateCandidate.model_validate_json(
        encoded_with_hash(FormTemplateCandidate, synthetic_template_v1()))
    period = contracts.FilingPeriodCreate.model_validate(
        {"period_start": "2030-01-01", "period_end": "2030-03-31", "period_label": "SYNTHETIC"})
    assert template.effective_from < period.period_start  # out of window; nothing rejects this
    assert "filing_period" not in contracts.TaxReturnDraftRead.model_fields


def test_s12_draft_creation_pins_form_version() -> None:
    create = contracts.TaxReturnDraftCreate.model_validate(
        {"calculation_id": CALC_ID, "expected_data_version": 1, "form_version": "synthetic-v1"})
    assert create.form_version == "synthetic-v1"
    with pytest.raises(ValidationError):
        contracts.TaxReturnDraftCreate.model_validate(
            {"calculation_id": CALC_ID, "expected_data_version": 1})


def test_gap_s12_draft_form_version_is_not_cross_checked_with_calculation() -> None:
    """GAP: a draft may pin a form_version different from its calculation's form_version."""
    draft = contracts.TaxReturnDraftRead.model_validate(synthetic_draft(form_version="synthetic-v2"))
    calculation = contracts.TaxCalculationRead.model_validate(synthetic_calculation())
    assert draft.form_version != calculation.form_version  # inconsistent; nothing rejects this


# ---------------------------------------------------------------------------
# 四、表间关系测试 (where a generic mechanism exists).
# ---------------------------------------------------------------------------

def test_r2_field_values_link_to_calculation_lines() -> None:
    calculation = contracts.TaxCalculationRead.model_validate(synthetic_calculation())
    draft = contracts.TaxReturnDraftRead.model_validate(synthetic_draft())
    assert draft.fields[0].calculation_line_key == calculation.lines[0].key


def test_gap_r2_field_value_is_not_compared_with_calculation_line() -> None:
    """GAP: the field value may differ from the linked calculation line amount."""
    draft = contracts.TaxReturnDraftRead.model_validate(
        synthetic_draft(fields=[synthetic_field_value(value="999999")]))
    assert draft.fields[0].value == "999999" and draft.fields[0].calculation_line_key == "SYNTHETIC_TEST_LINE_AMOUNT"


def test_r3_field_values_carry_evidence_references() -> None:
    draft = contracts.TaxReturnDraftRead.model_validate(synthetic_draft())
    ref = draft.fields[0].evidence[0]
    assert ref.kind == "tax_calculation" and ref.content_hash == SOURCE_HASH


def test_gap_r4_validation_rules_are_untyped_and_not_evaluated() -> None:
    """GAP: validation_rules is only dict[str, str] shape; no evaluator interprets it."""
    payload = synthetic_template_v1()
    payload["validation_rules"] = [{"expression": "SYNTHETIC_TEST_FIELD_AMOUNT >= 0"}]
    template = FormTemplateCandidate.model_validate_json(encoded_with_hash(FormTemplateCandidate, payload))
    assert template.validation_rules == [{"expression": "SYNTHETIC_TEST_FIELD_AMOUNT >= 0"}]
    malformed = synthetic_template_v1()
    malformed["validation_rules"] = [{"expression": 1}]
    with pytest.raises(ValidationError):
        FormTemplateCandidate.model_validate_json(encoded_with_hash(FormTemplateCandidate, malformed))


def test_gap_r7_draft_can_be_marked_approved_with_missing_materials() -> None:
    """GAP: the contract alone cannot stop a draft with missing materials from being
    marked approved. BE2-07/BE2-08 must add the server-side completeness gate."""
    draft = contracts.TaxReturnDraftRead.model_validate(synthetic_draft(
        status="approved", missing=["SYNTHETIC_TEST_MATERIAL"],
        blockers=[{"code": "SYNTHETIC_TEST_BLOCKER", "message": "SYNTHETIC_TEST_ONLY", "evidence": []}]))
    assert draft.status == "approved" and draft.missing_material_codes == ["SYNTHETIC_TEST_MATERIAL"]


def test_r7_blocking_state_can_be_expressed() -> None:
    draft = contracts.TaxReturnDraftRead.model_validate(synthetic_draft(
        status="blocked", missing=["SYNTHETIC_TEST_MATERIAL"],
        blockers=[{"code": "SYNTHETIC_TEST_BLOCKER", "message": "SYNTHETIC_TEST_ONLY", "evidence": []}]))
    assert draft.status == "blocked" and draft.blockers[0].code == "SYNTHETIC_TEST_BLOCKER"


# ---------------------------------------------------------------------------
# 五、版本测试.
# ---------------------------------------------------------------------------

def test_v1_template_preview_and_pinned_draft_creation() -> None:
    preview = preview_form_template(
        encoded_with_hash(FormTemplateCandidate, synthetic_template_v1()),
        known_sources=KNOWN_SOURCES, existing={})
    assert preview.outcome == "new" and preview.identity == ("SYNTHETIC_TEST_TEMPLATE", "synthetic-v1")
    create = contracts.TaxReturnDraftCreate.model_validate(
        {"calculation_id": CALC_ID, "expected_data_version": 1, "form_version": "synthetic-v1"})
    assert create.form_version == "synthetic-v1"


def test_v2_new_template_version_keeps_v1_mapping_separate() -> None:
    first = preview_form_template(
        encoded_with_hash(FormTemplateCandidate, synthetic_template_v1()),
        known_sources=KNOWN_SOURCES, existing={})
    existing = {first.identity: first.content_hash}
    second = preview_form_template(
        encoded_with_hash(FormTemplateCandidate, synthetic_template_v2()),
        known_sources=KNOWN_SOURCES, existing=existing)
    assert second.identity == ("SYNTHETIC_TEST_TEMPLATE", "synthetic-v2") and second.outcome == "new"
    assert existing[first.identity] == first.content_hash  # V1 mapping is not overwritten
    v1_keys = set(synthetic_template_v1()["fields"])
    v2_keys = set(synthetic_template_v2()["fields"])
    assert v1_keys != v2_keys  # the mapping change is version-scoped
    changed_v1 = synthetic_template_v1()
    changed_v1["fields"]["SYNTHETIC_TEST_FIELD_AMOUNT"]["required"] = False
    conflict = preview_form_template(
        encoded_with_hash(FormTemplateCandidate, changed_v1), known_sources=KNOWN_SOURCES, existing=existing)
    assert conflict.outcome == "version_conflict"


def test_v3_draft_retains_template_and_version_trace_fields() -> None:
    draft = contracts.TaxReturnDraftRead.model_validate(synthetic_draft())
    assert draft.form_version == "synthetic-v1"
    assert draft.draft_version == 1
    assert draft.content_hash == SOURCE_HASH
    assert draft.rule_versions == ["SYNTHETIC_TEST_RULE@synthetic-v1"]
    assert str(draft.calculation_id) == CALC_ID


def test_v4_review_request_pins_versions_and_hash() -> None:
    request = contracts.DraftReviewRequest.model_validate({
        "action": "approve", "expected_draft_version": 1, "expected_data_version": 1,
        "expected_content_hash": SOURCE_HASH})
    assert request.action == "approve"
    with pytest.raises(ValidationError):
        contracts.DraftReviewRequest.model_validate({
            "action": "approve", "expected_draft_version": 1, "expected_data_version": 1})
    with pytest.raises(ValidationError):
        contracts.DraftReviewRequest.model_validate({
            "action": "reject", "expected_draft_version": 1, "expected_data_version": 1,
            "expected_content_hash": SOURCE_HASH})


# ---------------------------------------------------------------------------
# MVP evidence-reference boundary (the only existing runtime evidence check).
# The MVP report is NOT a tax return draft; this only verifies the current boundary.
# ---------------------------------------------------------------------------

async def _create_report_with_refs(order_id: str, batch: dict, ticket: dict, match: dict,
                                   version: int, input_refs: list, output_refs: list):
    engine = make_engine(get_settings().database_url)
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            summary = {name: batch[name] for name in ("matched_count", "unmatched_count", "exception_count")}
            summary.update({"batch_id": batch["id"], "match_ids": [match["id"]],
                            "exception_ids": [ticket["id"]]})
            financial = {name: batch[name] for name in (
                "income_total_cents", "expense_total_cents", "net_cash_change_cents")}
            exception_summary = [{
                "exception_id": ticket["id"], "exception_type": ticket["exception_type"],
                "status": ticket["status"], "related_amount_cents": ticket["related_amount_cents"],
                "difference_cents": ticket["difference_cents"],
            }]
            task = await agent_service.create_task(session, AgentTaskCreate(
                order_id=order_id, agent_role="risk_delivery", task_type="report_draft",
                idempotency_key=f"report-v{version}", correlation_id=f"report-corr-{version}",
                input_payload={"order_id": order_id, "report_version": version,
                               "financial_summary": financial,
                               "reconciliation_summary": summary,
                               "exception_summary": exception_summary,
                               "evidence_references": input_refs, "unresolved_items": []},
            ))
            await agent_service.start_task(session, task.id)
            await agent_service.complete_task(session, task.id, {
                "order_id": order_id, "report_version": version, "report_content": "SYNTHETIC_TEST",
                "evidence_references": output_refs, "unresolved_items": [],
            })
            return await report_service.create_from_agent_task(session, task.id)
    finally:
        await engine.dispose()


def test_mvp_report_rejects_unknown_evidence_reference(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        batch, ticket, match = await make_batch_with_exception(client, order_id)
        with pytest.raises(AppError) as exc:
            await _create_report_with_refs(order_id, batch, ticket, match, 1,
                                           ["missing-evidence-ref"], ["missing-evidence-ref"])
        assert exc.value.code == "invalid_report_evidence"
        assert "record in this order" in exc.value.message

    exercise(tmp_path, monkeypatch, scenario)


def test_mvp_report_rejects_output_reference_missing_from_task_input(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        batch, ticket, match = await make_batch_with_exception(client, order_id)
        with pytest.raises(AppError) as exc:
            await _create_report_with_refs(order_id, batch, ticket, match, 1, [], [match["id"]])
        assert exc.value.code == "invalid_report_evidence"
        assert "task input" in exc.value.message

    exercise(tmp_path, monkeypatch, scenario)
