"""Explicit model replacement for API/worker integration tests only."""

import hashlib
import json
import re
from pathlib import Path

from app.intake.contracts import ImageSample, IntakeAnswer, PrecheckNarrative
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
        if schema is ImageSample:
            return ImageSample(
                file_id=re.search(r"file_id 必须为 ([a-f0-9-]+)", prompt)[1],
                category="invoice_image",
                readable=True,
                explanation="抽查图片类型为票据且可读。",
            )
        if schema is PrecheckNarrative:
            if "plan_materials" in named:
                manifest = json.loads(await named["list_materials"]())
                tasks = []
                for source in manifest:
                    if source["category"] == "archive":
                        tasks.append(
                            {"file_id": source["id"], "kind": "inspect_archive", "title": "查看压缩包内容"}
                        )
                    elif source["included"]:
                        tasks.append(
                            {
                                "file_id": source["id"],
                                "kind": "read_document",
                                "title": "读取 " + source["name"],
                            }
                        )
                tasks.append({"file_id": "", "kind": "check_materials", "title": "整理待确认事项"})
                await named["plan_materials"](tasks)
                for source in manifest:
                    if source["category"] == "archive":
                        await named["open_archive"](source["id"])
                    elif source["included"]:
                        reader = (
                            named["read_image"]
                            if source["type"].startswith("image/")
                            else named["read_document"]
                        )
                        observed = json.loads(await reader(source["id"]))
                        if observed.get("type") == "table" and observed.get("sheets"):
                            headers = observed["sheets"][0]["rows"][0]
                            if {"交易日期", "对方户名", "收支", "发生额"} <= set(headers):
                                tasks.append(
                                    {
                                        "file_id": source["id"],
                                        "kind": "normalize_statement",
                                        "title": "按实际列名整理原始流水",
                                    }
                                )
                                await named["plan_materials"](tasks)
                                await named["normalize_statement"](
                                    source["id"],
                                    {
                                        "transaction_date": "交易日期",
                                        "counterparty": "对方户名",
                                        "direction": "收支",
                                        "amount": "发生额",
                                    },
                                )
                await named["inspect_intake_materials"]()
                return PrecheckNarrative.model_validate_json(
                    await named["save_precheck_result"](
                        summary="已按待办读取材料，仅确认服务启动条件，正式处理仍可能发现异常。",
                        questions=[],
                        evidence_refs=[],
                    )
                )
            if "inspect_intake_materials" in named:
                await named["inspect_intake_materials"]()
                return PrecheckNarrative(
                    summary="已取得真实材料检查和抽查结果，等待保存预检。", questions=[], evidence_refs=[]
                )
            return PrecheckNarrative.model_validate_json(
                await named["save_precheck_result"](
                    summary="材料预检已完成，仅检查服务启动条件，正式处理仍可能发现异常。",
                    questions=[],
                    evidence_refs=[],
                )
            )
        if schema is IntakeAnswer:
            return IntakeAnswer(
                answer="请上传材料并确认工作室及账期，预检后点击服务卡确认创建订单。", evidence_refs=[]
            )
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
            if "plan_todos" in named:
                await named["plan_todos"](["核对客户问题与订单数据", "撰写定性答复"])
            context = json.loads(prompt.split("\n")[-1])["context"]
            refs = [context["exceptions"][0]["exception_no"]] if context["exceptions"] else []
            return ChatReply(
                answer="请查看当前订单的实际核对结果，未确认的事项仍需核实。", evidence_refs=refs
            )
        if "plan_todos" in named:
            await named["plan_todos"](["读取任务目标与真实数据", "调用业务工具完成处理", "核对成果与工具回执"])
        for name in ("process_invoice_batch", "reconcile_transactions", "create_report_draft"):
            if name in named:
                await named[name]()
        if "save_customer_message" in named:
            await named["save_customer_message"]("已收到本期材料，将按实际内容逐项处理。")
        if "save_customer_questions" in named:
            await named["save_customer_questions"]("请补充差额说明和缺失凭证，原因尚待核实。")
        if "save_risk_summary" in named:
            await named["save_risk_summary"]("当前差额、重复与缺票需要人工核实。")
        if "todo_status" in named:
            await named["todo_status"]("completed", [], "已完成本项处理。")
        return RoleResult(summary="已调用所需工具并保存成果", evidence_refs=[])
