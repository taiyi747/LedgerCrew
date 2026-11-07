"""Export a combined MVP + proposed P2 OpenAPI design document; never mounts P2 routes."""

import json
import sys
from copy import deepcopy
from pathlib import Path

from pydantic.json_schema import models_json_schema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from app.main import app  # noqa: E402

sys.path.insert(0, str(ROOT))
from contracts import schemas as s  # noqa: E402

# method, path, request, response, role, idempotency, version policy, success status
ENDPOINTS = [
    ("get", "/api/v1/studios/{studio_id}/tax-profiles", None, s.MerchantTaxProfileRead, "decision-pending:DEC-010/012/013", "n/a", "n/a", 200, True),
    ("post", "/api/v1/studios/{studio_id}/tax-profiles", s.MerchantTaxProfileCreate, s.MerchantTaxProfileRead, "decision-pending:DEC-010/012/013", "key", "new profile_version=1", 201, False),
    ("get", "/api/v1/tax-profiles/{profile_id}", None, s.MerchantTaxProfileRead, "decision-pending:DEC-010/012/013", "n/a", "n/a", 200, False),
    ("patch", "/api/v1/tax-profiles/{profile_id}", s.MerchantTaxProfileUpdate, s.MerchantTaxProfileRead, "decision-pending:DEC-010/012/013", "key", "If-Match profile_version", 200, False),
    ("get", "/api/v1/supported-scopes", None, s.SupportedScopeRead, "decision-pending:DEC-010/012/013", "n/a", "scope_version in result", 200, True),
    ("post", "/api/v1/supported-scopes/check", s.ScopeCheckRequest, s.ScopeCheckResponse, "decision-pending:DEC-010/012/013", "n/a", "scope_version in result", 200, False),
    ("post", "/api/v1/filing-tasks", s.FilingTaskCreate, s.FilingTaskRead, "decision-pending:DEC-010/012/013", "key", "initial data_version=1", 201, False),
    ("get", "/api/v1/filing-tasks", None, s.FilingTaskRead, "decision-pending:DEC-010/012/013", "n/a", "data_version in result", 200, True),
    ("get", "/api/v1/filing-tasks/{filing_task_id}", None, s.FilingTaskRead, "decision-pending:DEC-010/012/013", "n/a", "data_version in result", 200, False),
    ("post", "/api/v1/filing-tasks/{filing_task_id}/platform-imports", s.PlatformImportCreate, s.PlatformImportRead, "decision-pending:DEC-010/012/013", "key", "If-Match data_version", 201, False),
    ("get", "/api/v1/filing-tasks/{filing_task_id}/platform-imports", None, s.PlatformImportRead, "decision-pending:DEC-010/012/013", "n/a", "data_version in result", 200, True),
    ("get", "/api/v1/platform-imports/{import_id}", None, s.PlatformImportRead, "decision-pending:DEC-010/012/013", "n/a", "data_version in result", 200, False),
    ("get", "/api/v1/platform-imports/{import_id}/records", None, s.PlatformRecordRead, "decision-pending:DEC-010/012/013", "n/a", "data_version in result", 200, True),
    ("get", "/api/v1/filing-tasks/{filing_task_id}/settlement-batches", None, s.SettlementBatchRead, "decision-pending:DEC-010/012/013", "n/a", "data_version in result", 200, True),
    ("get", "/api/v1/settlement-batches/{batch_id}", None, s.SettlementBatchRead, "decision-pending:DEC-010/012/013", "n/a", "data_version in result", 200, False),
    ("get", "/api/v1/filing-tasks/{filing_task_id}/accounting-suggestions", None, s.AccountingSuggestionRead, "decision-pending:DEC-010/012/013", "n/a", "data_version in result", 200, True),
    ("post", "/api/v1/accounting-suggestions/{suggestion_id}/decisions", s.AccountingDecision, s.AccountingDecisionResult, "decision-pending:DEC-010/012/013", "key", "If-Match data_version", 200, False),
    ("get", "/api/v1/filing-tasks/{filing_task_id}/accounting-entries", None, s.AccountingEntryRead, "decision-pending:DEC-010/012/013", "n/a", "data_version in result", 200, True),
    ("get", "/api/v1/policy-sources", None, s.PolicySourceRead, "decision-pending:DEC-010/012/013", "n/a", "source_version in result", 200, True),
    ("get", "/api/v1/policy-rules", None, s.PolicyRuleRead, "decision-pending:DEC-010/012/013", "n/a", "rule_version in result", 200, True),
    ("get", "/api/v1/policy-rules/{rule_id}", None, s.PolicyRuleRead, "decision-pending:DEC-010/012/013", "n/a", "rule_version in result", 200, False),
    ("post", "/api/v1/policy-rules/{rule_id}/decisions", s.PolicyRuleDecision, s.PolicyRuleRead, "decision-pending:DEC-010/012/013", "key", "If-Match rule_version", 200, False),
    ("post", "/api/v1/filing-tasks/{filing_task_id}/tax-calculations", s.TaxCalculationRun, s.TaxCalculationRead, "decision-pending:DEC-010/012/013", "key", "If-Match data_version; pinned rule/form versions", 201, False),
    ("get", "/api/v1/filing-tasks/{filing_task_id}/tax-calculations", None, s.TaxCalculationRead, "decision-pending:DEC-010/012/013", "n/a", "all versions retained", 200, True),
    ("get", "/api/v1/tax-calculations/{calculation_id}", None, s.TaxCalculationRead, "decision-pending:DEC-010/012/013", "n/a", "immutable result", 200, False),
    ("post", "/api/v1/filing-tasks/{filing_task_id}/tax-return-drafts", s.TaxReturnDraftCreate, s.TaxReturnDraftRead, "decision-pending:DEC-010/012/013", "key", "If-Match data_version; pinned calculation/form", 201, False),
    ("get", "/api/v1/filing-tasks/{filing_task_id}/tax-return-drafts", None, s.TaxReturnDraftRead, "decision-pending:DEC-010/012/013", "n/a", "all versions retained", 200, True),
    ("get", "/api/v1/tax-return-drafts/{draft_id}", None, s.TaxReturnDraftRead, "decision-pending:DEC-010/012/013", "n/a", "immutable draft content", 200, False),
    ("post", "/api/v1/tax-return-drafts/{draft_id}/reviews", s.DraftReviewRequest, s.TaxReturnDraftRead, "decision-pending:DEC-010/012/013", "key", "If-Match draft_version and content hash", 200, False),
    ("post", "/api/v1/filing-tasks/{filing_task_id}/filing-packages", s.FilingPackagePrepare, s.FilingPackageRead, "decision-pending:DEC-010/012/013", "key", "If-Match data_version/draft_version", 201, False),
    ("get", "/api/v1/filing-tasks/{filing_task_id}/filing-packages", None, s.FilingPackageRead, "decision-pending:DEC-010/012/013", "n/a", "all versions retained", 200, True),
    ("get", "/api/v1/filing-packages/{package_id}", None, s.FilingPackageRead, "decision-pending:DEC-010/012/013", "n/a", "immutable manifest", 200, False),
    ("post", "/api/v1/filing-packages/{package_id}/actions", s.PackageAction, s.FilingPackageRead, "decision-pending:DEC-010/012/013", "key", "If-Match package_version and content hash", 200, False),
    ("get", "/api/v1/filing-packages/{package_id}/download", None, None, "decision-pending:DEC-010/012/013", "n/a", "immutable artifact", 200, False),
]

MODELS = [value for value in vars(s).values() if isinstance(value, type) and issubclass(value, s.StrictModel)]
_, definitions = models_json_schema([(model, "validation") for model in MODELS], ref_template="#/components/schemas/{model}")
spec = deepcopy(app.openapi())
spec["info"]["title"] = "LedgerCrew MVP + Phase 2 proposed contract"
spec["info"]["version"] = "2.0.0-draft"
spec["info"]["description"] = "P2 paths are design-only and are not mounted by server/app/main.py. Existing MVP paths are copied from the live app."
spec["components"]["schemas"].update(definitions["$defs"])
spec["components"]["securitySchemes"] = {
    "DevUserId": {"type": "apiKey", "in": "header", "name": "X-User-Id", "description": "MVP development/test identity only; production returns 503 until real auth is integrated."}
}

ERROR_CODES = {
    401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "business_blocked",
    412: "version_conflict", 422: "validation_error", 428: "precondition_required", 503: "authentication_unavailable",
}

FILTERS = {
    "/api/v1/filing-tasks": ["profile_id", "status"],
    "/api/v1/filing-tasks/{filing_task_id}/platform-imports": ["status"],
    "/api/v1/platform-imports/{import_id}/records": ["record_kind"],
    "/api/v1/filing-tasks/{filing_task_id}/settlement-batches": ["status"],
    "/api/v1/filing-tasks/{filing_task_id}/accounting-suggestions": ["status"],
    "/api/v1/policy-sources": ["region_code", "status"],
    "/api/v1/policy-rules": ["region_code", "filing_kind", "status"],
    "/api/v1/filing-tasks/{filing_task_id}/tax-calculations": ["status"],
    "/api/v1/filing-tasks/{filing_task_id}/tax-return-drafts": ["status"],
    "/api/v1/filing-tasks/{filing_task_id}/filing-packages": ["status"],
    "/api/v1/supported-scopes": ["region_code", "entity_type", "filing_kind", "platform_code", "status"],
}

for method, path, request, response, role, idem, version, success, many in ENDPOINTS:
    operation_id = method + "_" + path.removeprefix("/api/v1/").replace("/", "_").replace("{", "").replace("}", "").replace("-", "_")
    parameters = []
    for segment in path.split("/"):
        if segment.startswith("{"):
            parameters.append({"name": segment[1:-1], "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}})
    if many:
        parameters.extend([
            {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}},
            {"name": "cursor", "in": "query", "schema": {"type": "string"}},
        ])
        parameters.extend({"name": name, "in": "query", "schema": {"type": "string", **({"format": "uuid"} if name == "profile_id" else {})}}
                          for name in FILTERS.get(path, []))
    if method in {"post", "patch"} and idem == "key":
        parameters.append({"name": "Idempotency-Key", "in": "header", "required": True, "schema": {"type": "string", "minLength": 1, "maxLength": 100}})
    if method in {"post", "patch"} and "If-Match" in version:
        parameters.append({"name": "If-Match", "in": "header", "required": True, "schema": {"type": "string"}})
    if many:
        response_schema = {"type": "object", "required": ["items", "next_cursor"], "properties": {
            "items": {"type": "array", "items": {"$ref": f"#/components/schemas/{response.__name__}"}},
            "next_cursor": {"type": ["string", "null"]},
        }}
    elif response is None:
        response_schema = None
    else:
        response_schema = {"$ref": f"#/components/schemas/{response.__name__}"}
    success_content = {"application/json": {"schema": response_schema}} if response_schema else {"application/zip": {"schema": {"type": "string", "format": "binary"}}}
    op = {
        "tags": ["phase-2-proposed"], "operationId": operation_id,
        "summary": operation_id.replace("_", " "),
        "description": "PROPOSED, not implemented. See contracts/API.md for detailed business semantics.",
        "parameters": parameters, "security": [{"DevUserId": []}],
        "responses": {str(success): {"description": "Success", "content": success_content}},
        "x-ledgercrew-role": role, "x-ledgercrew-idempotency": idem,
        "x-ledgercrew-version-policy": version, "x-ledgercrew-status": "proposed",
    }
    if request:
        op["requestBody"] = {"required": True, "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{request.__name__}"}}}}
    for status, code in ERROR_CODES.items():
        op["responses"][str(status)] = {"description": code, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}, "example": {"error": {"code": code, "message": code, "blockers": []}}}}}
    spec["paths"].setdefault(path, {})[method] = op

# A filing-scoped source file is separate from MVP's order-scoped uploaded_files.
spec["paths"]["/api/v1/filing-tasks/{filing_task_id}/files"] = {
    "post": {
        "tags": ["phase-2-proposed"], "operationId": "upload_filing_file", "summary": "Upload filing source file",
        "description": "PROPOSED. File content validation and storage are backend-owned.",
        "security": [{"DevUserId": []}], "x-ledgercrew-role": "decision-pending:DEC-010/012/013", "x-ledgercrew-idempotency": "key",
        "x-ledgercrew-version-policy": "If-Match data_version", "x-ledgercrew-status": "proposed",
        "parameters": [
            {"name": "filing_task_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
            {"name": "Idempotency-Key", "in": "header", "required": True, "schema": {"type": "string"}},
            {"name": "If-Match", "in": "header", "required": True, "schema": {"type": "string"}},
        ],
        "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {"type": "object", "required": ["file"], "properties": {"file": {"type": "string", "format": "binary"}}}}}},
        "responses": {"201": {"description": "File accepted", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/FilingFileRead"}}}},
                      **{str(status): {"description": code, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}} for status, code in ERROR_CODES.items()}},
    }
}

output = ROOT / "contracts" / "openapi.json"
output.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {output} with {len(spec['paths'])} paths")
