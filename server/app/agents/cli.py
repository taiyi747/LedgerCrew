"""Standalone synthetic-fixture demonstration; model calls are real and explicit."""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path

from .checkpoints import create_checkpoint_storage
from .config import Settings
from .contracts import HumanReply, InvoiceExtraction, OrderInput, ReviewRequest, SupervisorDecision
from .demo import FixtureBackend
from .errors import AgentError
from .fixtures import create_fixtures
from .lease import ExecutionLease
from .runner import MiMoRunner, RequestBudget
from .workflow import build_workflow

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "fixtures" / "mvp"


def print_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


async def run_cli(args) -> dict:
    if args.command == "fixtures":
        return {"synthetic": True, "manifest": create_fixtures(FIXTURES)}
    settings = Settings.from_env()
    data_dir = settings.data_dir
    if not data_dir.is_absolute():
        data_dir = REPO / "server" / data_dir
    backend = FixtureBackend(data_dir, FIXTURES)
    template = OrderInput.model_validate_json((FIXTURES / "order.json").read_text(encoding="utf-8"))
    if args.command == "smoke":
        template.identity.order_id = "smoke-" + uuid.uuid4().hex[:12]
        template.identity.run_id = "smoke-run"
    if args.command in {"start", "smoke"}:
        existing = data_dir / template.identity.order_id / "order.json"
        if existing.exists():
            raise AgentError("样例订单已存在；请使用 status/resume，或配置新的 LEDGERCREW_DATA_DIR。")
        backend.put_order(template)
    order = await backend.load_order(template.identity.order_id)
    if args.command == "smoke":
        runner = MiMoRunner(settings)
        budget = RequestBudget(backend, order.identity, settings.max_requests)
        text = await runner.generate(
            "supervisor", "安排识别票据，next_action 为 extract。", SupervisorDecision, budget
        )
        file = order.files[0]
        extraction = await runner.generate(
            "invoice",
            "提取票据，未知字段留空。",
            InvoiceExtraction,
            budget,
            image=(await backend.read_invoice(order.identity.order_id, file.id), file.mime_type),
        )
        return {
            "mode": "real_mimo_synthetic_fixtures",
            "pro_text": text.model_dump(),
            "flash_image": extraction.model_dump(mode="json"),
            "usage": await backend.load_artifact(order.identity, "usage"),
        }
    if args.command == "status":
        return {
            "identity": order.identity.model_dump(),
            "review": await backend.load_artifact(order.identity, "review"),
            "report": await backend.load_artifact(order.identity, "report"),
            "approval": await backend.load_artifact(order.identity, "approval"),
            "usage": await backend.load_artifact(order.identity, "usage"),
        }
    storage = create_checkpoint_storage(
        data_dir / order.identity.order_id / order.identity.run_id / "checkpoints"
    )
    name = "ledgercrew-" + order.identity.order_id + "-" + order.identity.run_id
    workflow = build_workflow(backend, storage, name)
    if args.command == "start":
        result = await workflow.run(order.identity)
    elif args.command == "retry":
        checkpoint = await storage.get_latest(workflow_name=name)
        if checkpoint is None:
            result = await workflow.run(order.identity)
        else:
            result = await workflow.run(checkpoint_id=checkpoint.checkpoint_id)
    else:
        raw = await backend.load_artifact(order.identity, "review")
        if not raw:
            raise AgentError("没有可恢复的人工待办。")
        request = ReviewRequest.model_validate(raw)
        reply = HumanReply(
            identity=request.identity,
            request_id=args.request_id,
            action="submit_information" if args.command == "supplement" else args.action,
            comment=args.comment,
            report_version=getattr(args, "report_version", None),
        )
        # Validate before updating sample input or loading the checkpoint.
        from .workflow import validate_reply

        validate_reply(request, reply)
        approval = await backend.load_artifact(order.identity, "approval")
        if (
            reply.action == "approve_delivery"
            and approval
            and approval["approval_request_id"] == reply.request_id
            and approval["report"]["report_version"] == reply.report_version
            and approval["identity"] == order.identity.model_dump()
        ):
            return {
                "mode": "real_mimo_synthetic_fixtures",
                "replayed": True,
                "outputs": [approval],
                "pending": [],
                "usage": await backend.load_artifact(order.identity, "usage"),
            }
        checkpoint = await storage.get_latest(workflow_name=name)
        if checkpoint is None:
            raise AgentError("缺少检查点。")
        if args.command == "supplement":
            order.identity.revision += 1
            order.customer_notes.append(args.comment)
            backend.put_order(order)
        result = await workflow.run(
            checkpoint_id=checkpoint.checkpoint_id, responses={request.request_id: reply}
        )
    checkpoint = await storage.get_latest(workflow_name=name)
    return {
        "mode": "real_mimo_synthetic_fixtures",
        "workflow_name": name,
        "checkpoint_id": checkpoint.checkpoint_id if checkpoint else None,
        "pending": [
            {"request_id": e.request_id, "request": e.data.model_dump(mode="json")}
            for e in result.get_request_info_events()
        ],
        "outputs": [
            o.model_dump(mode="json") if hasattr(o, "model_dump") else o for o in result.get_outputs()
        ],
        "usage": await backend.load_artifact(order.identity, "usage"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="LedgerCrew AI：真实 MiMo＋合成样例后端")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("fixtures", "start", "smoke", "status", "retry"):
        commands.add_parser(command)
    resume = commands.add_parser("resume")
    resume.add_argument("--request-id", required=True)
    resume.add_argument(
        "--action",
        required=True,
        choices=["request_info", "keep_flagged", "approve_delivery", "revise_report"],
    )
    resume.add_argument("--report-version", type=int)
    resume.add_argument("--comment", default="")
    supplement = commands.add_parser("supplement")
    supplement.add_argument("--request-id", required=True)
    supplement.add_argument("--comment", required=True)
    args = parser.parse_args()
    try:
        if args.command in {"start", "retry", "resume", "supplement"}:
            settings = Settings.from_env()
            data_dir = settings.data_dir
            if not data_dir.is_absolute():
                data_dir = REPO / "server" / data_dir
            with ExecutionLease(data_dir / "demo-order" / "demo-run" / "execution.lock"):
                print_json(asyncio.run(run_cli(args)))
        else:
            print_json(asyncio.run(run_cli(args)))
    except AgentError as error:
        print_json({"status": "failed", "error": str(error)})
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
