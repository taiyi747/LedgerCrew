"""Generate validated, scenario-labelled frontend mock responses for major P2 APIs."""

import json
from pathlib import Path

from contracts import schemas as s

HERE = Path(__file__).resolve().parent
OUT = HERE / "examples"
OUT.mkdir(exist_ok=True)


def uid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


NOW = "2026-11-07T04:00:00Z"
HASH = "a" * 64

profile = dict(id=uid(1), studio_id=uid(2), registered_name="示例商户（Mock）", region_code="REGION_TBD",
               entity_type="ENTITY_TBD", taxpayer_identity=None, tax_identifier=None,
               effective_from="2026-10-01", effective_to=None, profile_version=1,
               created_at=NOW, updated_at=NOW)
scope = dict(id=uid(3), region_code="REGION_TBD", entity_type="ENTITY_TBD", taxpayer_identity=None,
             filing_kind="FILING_KIND_TBD", platform_code="PLATFORM_TBD", platform_format_version="FORMAT_TBD",
             status="draft", scope_version=1, form_version=None, verified_at=None,
             unsupported_reason="首个场景尚待三人确认", required_materials=[], created_at=NOW)
period = dict(id=uid(4), period_start="2026-10-01", period_end="2026-10-31", period_label="2026-10", created_at=NOW)
task = dict(id=uid(5), profile_id=uid(1), scope_id=uid(3), filing_period=period, source_order_id=None,
            status="collecting_materials", data_version=1, scope_version=1,
            blockers=[dict(code="scope_unverified", message="支持范围待核实", evidence=[])], created_at=NOW, updated_at=NOW)
platform_import = dict(id=uid(6), filing_task_id=uid(5), filing_file_id=uid(7), platform_code="PLATFORM_TBD",
                       format_version="FORMAT_TBD", status="needs_mapping", total_rows=0, accepted_rows=0,
                       duplicate_rows=0, rejected_rows=0, data_version=1,
                       errors=[dict(code="mapping_required", message="导出格式待确认", evidence=[])], created_at=NOW)
batch = dict(id=uid(8), filing_task_id=uid(5), platform_code="PLATFORM_TBD", external_batch_id="MOCK-BATCH-001",
             settlement_date=None, expected_cents=None, received_cents=None, difference_cents=None,
             status="needs_review", data_version=1, allocations=[], bank_transaction_evidence=[], created_at=NOW)
evidence = [dict(kind="platform_record", id=uid(9), locator="row:1", content_hash=HASH)]
suggestion = dict(id=uid(10), filing_task_id=uid(5), platform_record_id=uid(9),
                  proposed_category="classification_pending", proposed_account_code=None,
                  rationale="仅供界面示例，尚待人工分类", confidence="0.50", evidence=evidence,
                  data_version=1, source_task_id=None, status="proposed", suggestion_version=1, created_at=NOW)
source = dict(id=uid(11), title="官方来源占位（Mock）", issuing_authority="待核实",
              official_url="https://example.invalid/official-source-placeholder", published_on=None,
              effective_from=None, effective_to=None, region_code="REGION_TBD", snapshot_file_id=None,
              fetched_at=NOW, content_hash=HASH, source_version=1, status="candidate", created_at=NOW)
rule = dict(id=uid(12), source_ids=[uid(11)], rule_key="RULE_TBD", region_code="REGION_TBD",
            entity_type="ENTITY_TBD", taxpayer_identity=None, filing_kind="FILING_KIND_TBD",
            period_start="2026-10-01", period_end=None, form_version=None, parameters={},
            explanation="规则候选占位，不能用于计算", evidence=[dict(kind="policy_source", id=uid(11))],
            rule_version="candidate-1", status="candidate", approved_by=None, approved_at=None, created_at=NOW)
calculation = dict(id=uid(13), filing_task_id=uid(5), status="blocked", data_version=1,
                   rule_versions=[], form_version="FORM_TBD", calculation_version=1,
                   input_hash=HASH, lines=[], blockers=[dict(code="rule_missing", message="尚无已批准规则", evidence=[])],
                   created_at=NOW)
draft = dict(id=uid(14), filing_task_id=uid(5), calculation_id=uid(13), form_version="FORM_TBD",
             draft_version=1, data_version=1, rule_versions=[], status="blocked", fields=[],
             missing_material_codes=[], blockers=[dict(code="form_unverified", message="表单版本待核实", evidence=[])],
             content_hash=HASH, approved_by=None, approved_at=None, created_at=NOW)
package = dict(id=uid(15), filing_task_id=uid(5), draft_id=uid(14), draft_version=1,
               data_version=1, rule_versions=[], form_version="FORM_TBD", package_version=1,
               status="prepared", manifest=[], content_hash=HASH, approved_by=None,
               approved_at=None, published_at=None, created_at=NOW)

CASES = {
    "tax_profiles": ("GET /api/v1/tax-profiles/{profile_id}", s.MerchantTaxProfileRead, profile),
    "supported_scopes": ("GET /api/v1/supported-scopes", s.SupportedScopeRead, scope),
    "filing_tasks": ("GET /api/v1/filing-tasks/{filing_task_id}", s.FilingTaskRead, task),
    "platform_imports": ("GET /api/v1/platform-imports/{import_id}", s.PlatformImportRead, platform_import),
    "settlement_batches": ("GET /api/v1/settlement-batches/{batch_id}", s.SettlementBatchRead, batch),
    "accounting_suggestions": ("GET /api/v1/filing-tasks/{filing_task_id}/accounting-suggestions", s.AccountingSuggestionRead, suggestion),
    "policy_rules": ("GET /api/v1/policy-rules/{rule_id}", s.PolicyRuleRead, rule),
    "tax_calculations": ("GET /api/v1/tax-calculations/{calculation_id}", s.TaxCalculationRead, calculation),
    "tax_return_drafts": ("GET /api/v1/tax-return-drafts/{draft_id}", s.TaxReturnDraftRead, draft),
    "filing_packages": ("GET /api/v1/filing-packages/{package_id}", s.FilingPackageRead, package),
}

for name, (operation, model, body) in CASES.items():
    validated = model.model_validate(body).model_dump(mode="json")
    is_list_operation = name in {"supported_scopes", "accounting_suggestions"}
    if name in {"supported_scopes", "policy_rules"}:
        denied_status, denied_code, denied_message = 401, "unauthorized", "Authentication required"
    elif name in {"tax_calculations", "tax_return_drafts"}:
        denied_status, denied_code, denied_message = 403, "forbidden", "Action not permitted"
    else:
        denied_status, denied_code, denied_message = 404, "not_found", "Resource not found"
    mock = {
        "operation": operation,
        "success": {"status": 200, "body": {"items": [validated], "next_cursor": None} if is_list_operation else validated},
        "empty": {"status": 200, "body": {"items": [], "next_cursor": None}},
        "validation_error": {"status": 422, "body": {"error": {"code": "validation_error", "message": "Invalid request", "blockers": []}}},
        "forbidden": {"status": denied_status, "body": {"error": {"code": denied_code, "message": denied_message, "blockers": []}}},
        "business_blocked": {"status": 409, "body": {"error": {"code": "business_blocked", "message": "Prerequisite is incomplete", "blockers": [
            {"code": "prerequisite_missing", "message": "待人工确认支持范围或来源", "evidence": []}]}}},
    }
    s.ErrorResponse.model_validate(mock["validation_error"]["body"])
    s.ErrorResponse.model_validate(mock["forbidden"]["body"])
    s.ErrorResponse.model_validate(mock["business_blocked"]["body"])
    (OUT / f"{name}.json").write_text(json.dumps(mock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

(OUT / "policy_sources.json").write_text(json.dumps({
    "operation": "GET /api/v1/policy-sources", "success": {"status": 200, "body": {"items": [s.PolicySourceRead.model_validate(source).model_dump(mode="json")], "next_cursor": None}},
    "empty": {"status": 200, "body": {"items": [], "next_cursor": None}},
    "validation_error": {"status": 422, "body": {"error": {"code": "validation_error", "message": "Invalid request", "blockers": []}}},
    "forbidden": {"status": 401, "body": {"error": {"code": "unauthorized", "message": "Authentication required", "blockers": []}}},
    "business_blocked": {"status": 409, "body": {"error": {"code": "source_unavailable", "message": "Official source unavailable", "blockers": []}}},
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {len(CASES) + 1} mock files")
