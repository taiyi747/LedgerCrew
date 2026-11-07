# ruff: noqa: B008
from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AppError
from app.core.security import Principal, assert_owner, get_current_principal
from app.db.session import get_session
from app.live import service
from app.live.contracts import ROLES, MessageCreate, RunCreate
from app.live.models import Delegation, OrderMessage, WorkflowArtifact, WorkflowRun
from app.models import AgentTask, Order, UploadedFile, WorkflowEvent
from app.services.access import order_for_user

router = APIRouter(prefix="/api/v1", tags=["live"])
assets = APIRouter()


def run_read(run):
    if run is None:
        return None
    return {
        k: getattr(run, k)
        for k in (
            "id",
            "order_id",
            "kind",
            "status",
            "stage",
            "input_revision",
            "wait_reason",
            "requests_used",
            "request_limit",
            "created_at",
            "updated_at",
        )
    }


@router.post("/orders/{order_id}/runs", status_code=202)
async def start(
    order_id: str,
    data: RunCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    return run_read(
        await service.start_run(session, order_id, principal, data.idempotency_key, data.expected_revision)
    )


@router.get("/orders/{order_id}/runs/current")
async def current(
    order_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    await order_for_user(session, order_id, principal)
    run = await service.current_run(session, order_id)
    if not run:
        return None
    result = run_read(run)
    result["batch_current"] = (await service.snapshot(session, run.id))["batch_fresh"]
    if run.status == "failed":
        result["error"] = (
            run.error if principal.role == "owner" else "本次处理未能完成，请重试或联系老板检查。"
        )
    return result


@router.get("/orders/{order_id}/invoices")
async def invoices(
    order_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    from app.repositories.reconciliation import list_invoices
    from app.schemas.reconciliation import InvoiceRecordRead

    await order_for_user(session, order_id, principal)
    return [InvoiceRecordRead.model_validate(item) for item in await list_invoices(session, order_id)]


@router.post("/runs/{run_id}/retry", status_code=202)
async def retry(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    run = await session.get(WorkflowRun, run_id)
    if not run:
        raise AppError("not_found", "Run not found", 404)
    order = await order_for_user(session, run.order_id, principal)
    if run.status not in {"failed", "paused"}:
        return run_read(run)
    if run.requests_used >= run.request_limit:
        raise AppError("request_budget_exhausted", "本次运行请求预算已用尽，请人工处理。", 409)
    run.status, run.error, run.stage = "queued", None, "supervisor"
    if run.kind == "processing" and order.status != "delivered":
        order.status = "processing"
    failed = (
        await session.scalars(
            select(Delegation).where(Delegation.workflow_run_id == run.id, Delegation.status == "failed")
        )
    ).all()
    for item in failed:
        item.attempt_count = 0  # Human retry authorizes new attempts, not a budget reset or direct execution.
    run.input_revision = order.input_revision
    await session.commit()
    return run_read(run)


@router.get("/orders/{order_id}/messages")
async def messages(
    order_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    await order_for_user(session, order_id, principal)
    rows = (
        await session.scalars(
            select(OrderMessage).where(OrderMessage.order_id == order_id).order_by(OrderMessage.created_at)
        )
    ).all()
    return [
        {
            k: getattr(m, k)
            for k in (
                "id",
                "role",
                "content",
                "status",
                "file_ids",
                "evidence_refs",
                "workflow_run_id",
                "input_revision",
                "created_at",
            )
        }
        for m in rows
    ]


@router.post("/orders/{order_id}/messages", status_code=202)
async def message(
    order_id: str,
    data: MessageCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    order = await order_for_user(session, order_id, principal)
    existing = await session.scalar(
        select(OrderMessage).where(
            OrderMessage.order_id == order_id, OrderMessage.client_message_id == data.client_message_id
        )
    )
    if existing:
        return {"id": existing.id, "workflow_run_id": existing.workflow_run_id}
    for file_id in data.file_ids:
        file = await session.get(UploadedFile, file_id)
        if not file or file.order_id != order.id:
            raise AppError("invalid_message_file", "消息附件不属于当前订单。", 422)
    user = OrderMessage(
        order_id=order_id,
        role="user",
        content=data.content,
        file_ids=data.file_ids,
        client_message_id=data.client_message_id,
        input_revision=order.input_revision,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(OrderMessage).where(
                OrderMessage.order_id == order_id, OrderMessage.client_message_id == data.client_message_id
            )
        )
        if existing:
            return {"id": existing.id, "workflow_run_id": existing.workflow_run_id}
        raise
    if data.intent == "question":
        run = WorkflowRun(
            order_id=order.id,
            kind="chat",
            status="queued",
            input_revision=order.input_revision,
            idempotency_key="chat:" + data.client_message_id,
            created_by=principal.user_id,
            request_limit=6,
            source_message_id=user.id,
        )
        session.add(run)
        await session.flush()
        user.workflow_run_id = run.id
    await service.event(session, order.id, "message.created", {"message_id": user.id})
    await session.commit()
    return {"id": user.id, "workflow_run_id": user.workflow_run_id}


@router.get("/templates/statement.csv")
async def template():
    return Response(
        "\ufefftransaction_date,counterparty,direction,amount,description,external_id\n"
        "2026-10-10,示例交易方,OUT,108.00,示例付款,example-001\n",
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="statement-template.csv"'},
    )


@router.get("/owner/dashboard")
async def dashboard(
    order_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    assert_owner(principal)
    orders = list((await session.scalars(select(Order).order_by(Order.created_at.desc()).limit(100))).all())
    chosen = order_id or (orders[0].id if orders else None)
    run = await service.current_run(session, chosen) if chosen else None
    state = await service.snapshot(session, run.id) if run else None
    delegations = (
        list(
            (
                await session.scalars(
                    select(Delegation).where(Delegation.order_id == chosen).order_by(Delegation.created_at)
                )
            ).all()
        )
        if chosen
        else []
    )
    supervisor_statuses = (
        list(
            (
                await session.scalars(
                    select(AgentTask.status).where(
                        AgentTask.order_id == chosen,
                        AgentTask.agent_name == "supervisor",
                        AgentTask.workflow_run_id.is_not(None),
                    )
                )
            ).all()
        )
        if chosen
        else []
    )
    agents = []
    for role, meta in ROLES.items():
        mine = [d for d in delegations if d.agent_role == role]
        last = mine[-1] if mine else None
        status = last.status if last else "idle"
        if role == "supervisor" and run:
            status = (
                run.status if run.stage == "supervisor" or run.status != "running" else "waiting_children"
            )
        agents.append(
            {
                "id": role,
                **meta,
                "status": status,
                "current_task": last.goal if last else None,
                "queued": supervisor_statuses.count("queued")
                if role == "supervisor"
                else sum(d.status == "queued" for d in mine),
                "completed": supervisor_statuses.count("succeeded")
                if role == "supervisor"
                else sum(d.status == "succeeded" for d in mine),
                "failed": supervisor_statuses.count("failed")
                if role == "supervisor"
                else sum(d.status == "failed" for d in mine),
            }
        )
    latest_report = state.get("report") if state else None
    risk = await service.artifact(session, run.id, "risk") if run else None
    questions = await service.artifact(session, run.id, "questions") if run else None
    heartbeat_file = (
        Path(
            os.environ.get("LEDGERCREW_LIVE_DATA_DIR", str(Path(__file__).resolve().parents[2] / "data/live"))
        )
        / "heartbeat.json"
    )
    heartbeat = None
    if heartbeat_file.exists():
        with contextlib.suppress(ValueError):
            heartbeat = json.loads(heartbeat_file.read_text(encoding="utf-8"))
    return {
        "orders": [
            {
                k: getattr(o, k)
                for k in (
                    "id",
                    "order_no",
                    "status",
                    "input_revision",
                    "period_start",
                    "period_end",
                    "studio_id",
                )
            }
            for o in orders
        ],
        "selected_order_id": chosen,
        "run": run_read(run),
        "agents": agents,
        "exceptions": state["exceptions"] if state else [],
        "report": latest_report,
        "next_report_version": (latest_report["version"] + 1) if latest_report else 1,
        "questions": questions.payload if questions else None,
        "risk": risk.payload if risk else None,
        "worker": heartbeat,
        "summary": {
            "orders": len(orders),
            "processing": sum(o.status == "processing" for o in orders),
            "delivered": sum(o.status == "delivered" for o in orders),
            "waiting": sum(o.status in {"awaiting_customer", "awaiting_owner_review"} for o in orders),
        },
    }


@router.get("/owner/agents/{role}/trace")
async def trace(
    role: str,
    order_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    assert_owner(principal)
    if role not in ROLES:
        raise AppError("not_found", "Agent not found", 404)
    query = select(AgentTask).where(AgentTask.agent_name == role, AgentTask.workflow_run_id.is_not(None))
    if order_id:
        query = query.where(AgentTask.order_id == order_id)
    tasks = (await session.scalars(query.order_by(AgentTask.created_at.desc()).limit(30))).all()
    ds = (
        await session.scalars(
            select(Delegation)
            .where(Delegation.agent_role == role, *([Delegation.order_id == order_id] if order_id else []))
            .order_by(Delegation.created_at.desc())
            .limit(30)
        )
    ).all()
    decisions = []
    if role == "supervisor":
        query_decisions = (
            select(WorkflowArtifact).join(WorkflowRun).where(WorkflowArtifact.kind == "decision")
        )
        if order_id:
            query_decisions = query_decisions.where(WorkflowRun.order_id == order_id)
        decisions = [
            a.payload
            for a in (
                await session.scalars(query_decisions.order_by(WorkflowArtifact.created_at.desc()).limit(30))
            ).all()
        ]
    return {
        "decisions": decisions,
        "tasks": [
            {
                k: getattr(t, k)
                for k in (
                    "id",
                    "order_id",
                    "task_type",
                    "status",
                    "started_at",
                    "ended_at",
                    "delegation_id",
                    "error_message",
                )
            }
            for t in tasks
        ],
        "delegations": [
            {
                k: getattr(d, k)
                for k in (
                    "id",
                    "order_id",
                    "workflow_run_id",
                    "decision_id",
                    "agent_role",
                    "task_type",
                    "goal",
                    "input_refs",
                    "input_revision",
                    "status",
                    "result",
                    "receipts",
                    "error",
                )
            }
            for d in ds
        ],
    }


@router.get("/owner/events/stream")
async def owner_stream(
    request: Request,
    after_id: int = 0,
    follow: bool = True,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    assert_owner(principal)
    sessions = async_sessionmaker(session.bind, expire_on_commit=False)

    async def events():
        cursor = max(0, after_id)
        while True:
            async with sessions() as polling:
                rows = (
                    await polling.scalars(
                        select(WorkflowEvent)
                        .where(WorkflowEvent.id > cursor)
                        .order_by(WorkflowEvent.id)
                        .limit(100)
                    )
                ).all()
            for row in rows:
                cursor = row.id
                yield f"id: {cursor}\nevent: update\ndata: {json.dumps({'event_id': cursor, 'order_id': row.order_id, 'event_type': row.event_type, 'payload': row.payload}, ensure_ascii=False)}\n\n"
            if not follow or await request.is_disconnected():
                break
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform"}
    )


@assets.get("/console/")
@assets.get("/console/{asset_path:path}")
async def console(asset_path: str = "index.html"):
    asset_path = asset_path or "index.html"
    allowed = {
        "index.html",
        "dashboard.html",
        "css/style.css",
        "js/i18n.js",
        "js/illustrations.js",
        "js/live.js",
    }
    if asset_path not in allowed:
        raise AppError("not_found", "Asset not found", 404)
    root = Path(__file__).resolve().parents[3] / "HTML" / "owner"
    return FileResponse(root / asset_path)
