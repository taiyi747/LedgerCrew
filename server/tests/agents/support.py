from __future__ import annotations

import hashlib
import json

from app.agents.contracts import (
    CustomerDraft,
    InvoiceExtraction,
    ReconciliationAcknowledgement,
    ReportNarrative,
    SupervisorDecision,
)


class ScriptedRunner:
    """Test double only. Never imported by production runner/workflow/CLI."""

    def __init__(self, fixture_dir):
        expected = json.loads((fixture_dir / "expected_extractions.json").read_text(encoding="utf-8"))
        self.extractions = {}
        for record in expected:
            record = dict(record)
            file_id = record.pop("file_id")
            digest = hashlib.sha256((fixture_dir / (file_id + ".png")).read_bytes()).hexdigest()
            self.extractions[digest] = record
        self.calls = []

    async def generate(self, role, prompt, schema, budget, *, image=None, tools=None):
        await budget.reserve()
        self.calls.append(role)
        if role == "supervisor":
            return SupervisorDecision(next_action="extract", explanation="处理已提供的票据材料")
        if role == "invoice":
            raw = self.extractions.get(hashlib.sha256(image[0]).hexdigest())
            if raw:
                return InvoiceExtraction.model_validate(raw)
            return InvoiceExtraction(
                invoice_number=None,
                date=None,
                counterparty=None,
                amount_text=None,
                uncertain_fields=["amount_text"],
                evidence_text="无法读取金额",
            )
        if role == "reconciliation":
            await tools[0]()
            return ReconciliationAcknowledgement(summary="已按工具结果整理核对事项")
        if role == "customer_service":
            return CustomerDraft(question="请核实票据与付款差异，并补充缺失票据。", evidence_refs=[])
        if role == "delivery":
            return ReportNarrative(
                summary="核对已完成，未解决事项仍需核实。",
                next_steps=["请按异常清单补充材料。"],
                evidence_notes=[],
            )
        raise AssertionError(role)
