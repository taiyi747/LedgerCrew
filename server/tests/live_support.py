"""Explicit model replacement for API/worker integration tests only."""

import hashlib
import json
import re
from pathlib import Path

from app.integrations.agents.contracts import InvoiceExtractionOutput, ReportDraftOutput
from app.live.contracts import Assignment, ChatReply, RoleResult, SupervisorDecision


class LiveScriptedRunner:
    def __init__(self):
        root = Path(__file__).resolve().parents[2] / "fixtures/mvp"
        records = json.loads((root / "expected_extractions.json").read_text(encoding="utf-8"))
        self.images = {
            hashlib.sha256((root / (item["file_id"] + ".png")).read_bytes()).hexdigest(): item
            for item in records
        }
        self.calls = []

    async def generate(self, role, prompt, schema, budget, *, tools=None, image=None):
        await budget.reserve()
        self.calls.append((role, schema.__name__))
        named = {tool.__name__: tool for tool in tools or []}
        if schema is SupervisorDecision:
            state = json.loads(prompt.split("\n")[-1])
            eligible = state["eligible_tasks"]
            if eligible:
                task = eligible[0]
                from app.live.contracts import TASK_ROLE

                await named["delegate_tasks"](
                    [
                        Assignment(
                            agent_role=TASK_ROLE[task], task_type=task, goal="处理当前已确认范围的真实任务"
                        ).model_dump()
                    ]
                )
                return SupervisorDecision(action="delegated", summary="已实际调用派单工具")
            if (state["kind"] == "chat" and state["chat_done"]) or (
                state["report"] and state["report"]["fresh"] and state["report"]["status"] == "published"
            ):
                await named["complete_workflow"]()
                await named["complete_workflow"]()  # Simulate repeated tool call after JSON correction.
                return SupervisorDecision(action="completed", summary="已验证完成条件")
            if state["customer_waiting"]:
                await named["wait_for_customer"]("等待客户补充")
                return SupervisorDecision(action="waiting_customer", summary="等待客户")
            await named["request_owner_review"]("需要老板决定")
            await named["request_owner_review"]("需要老板决定")
            return SupervisorDecision(action="waiting_owner", summary="等待老板")
        if schema is InvoiceExtractionOutput:
            raw = self.images[hashlib.sha256(image[0]).hexdigest()]
            file_id = re.search(r"file_id 必须是 ([a-f0-9-]+)", prompt)[1]
            return InvoiceExtractionOutput(
                file_id=file_id,
                invoice_number=raw["invoice_number"],
                issue_date=raw["date"],
                seller=raw["counterparty"],
                buyer="松石设计工作室",
                total_amount=raw["amount_text"],
                confidence=0.99,
                missing_fields=["amount", "tax_amount", "invoice_type"],
                extraction_status="needs_review",
            )
        if schema is ReportDraftOutput:
            data = json.loads(prompt.split("\n")[-1])
            return ReportDraftOutput(
                order_id=data["order_id"],
                report_version=data["report_version"],
                report_content="已按照后端记录整理核对报告，未解决事项保留披露。",
                evidence_references=data["evidence_references"],
                unresolved_items=["请核实尚未确认的凭证。"],
            )
        if schema is ChatReply:
            context = json.loads(prompt.split("\n")[-1])["context"]
            refs = [context["exceptions"][0]["exception_no"]] if context["exceptions"] else []
            return ChatReply(
                answer="请查看当前订单的实际核对结果，未确认的事项仍需核实。", evidence_refs=refs
            )
        for name in ("process_invoice_batch", "reconcile_transactions", "create_report_draft"):
            if name in named:
                await named[name]()
        if "save_customer_message" in named:
            await named["save_customer_message"]("已收到本期材料，将按实际内容逐项处理。")
        if "save_customer_questions" in named:
            await named["save_customer_questions"]("请补充差额说明和缺失凭证，原因尚待核实。")
        if "save_risk_summary" in named:
            await named["save_risk_summary"]("当前差额、重复与缺票需要人工核实。")
        return RoleResult(summary="已调用所需工具并保存成果", evidence_refs=[])
