# ruff: noqa: B008
from __future__ import annotations

import asyncio
import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AppError
from app.core.security import Principal, assert_owner, get_current_principal
from app.db.session import get_session
from app.intake import service
from app.intake.contracts import (
    ConfirmCreate,
    ConfirmResult,
    FileUpdate,
    IntakeCreate,
    IntakeSnapshot,
    JobQueued,
    MessageCreate,
    PrecheckCreate,
    ProfileUpdate,
)
from app.intake.models import IntakeEvent, IntakeFile, IntakeMessage, IntakeSession
from app.storage.local import get_storage

router = APIRouter(prefix="/api/v1", tags=["intake"])


async def editable(session, intake_id, principal):
    item = await service.owned(session, intake_id, principal)
    if principal.role != "customer":
        raise AppError("forbidden", "老板入口只读查看接洽，材料与下单由客户确认。", 403)
    return item


@router.get("/services")
async def services():
    return [service.service_definition()]


@router.post("/intakes", status_code=201, response_model=IntakeSnapshot)
async def create(
    data: IntakeCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    item = await service.create(session, principal)
    return await service.snapshot(session, item, get_storage())


@router.get("/intakes")
async def index(
    session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)
):
    q = select(IntakeSession).order_by(IntakeSession.created_at.desc())
    if principal.role != "owner":
        q = q.where(IntakeSession.owner_user_id == principal.user_id)
    return [
        {
            k: getattr(x, k)
            for k in (
                "id",
                "status",
                "revision",
                "studio_name",
                "period_start",
                "period_end",
                "order_id",
                "created_at",
            )
        }
        for x in (await session.scalars(q)).all()
    ]


@router.get("/intakes/{intake_id}", response_model=IntakeSnapshot)
async def get(
    intake_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    return await service.snapshot(
        session,
        await service.owned(session, intake_id, principal),
        get_storage(),
        owner=principal.role == "owner",
    )


@router.patch("/intakes/{intake_id}", response_model=IntakeSnapshot)
async def profile(
    intake_id: str,
    data: ProfileUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    item = await editable(session, intake_id, principal)
    await service.profile(session, item, data, principal)
    return await service.snapshot(session, item, get_storage())


@router.post("/intakes/{intake_id}/files", status_code=201, response_model=IntakeSnapshot)
async def upload(
    intake_id: str,
    expected_revision: int = Form(...),
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    item = await editable(session, intake_id, principal)
    await service.upload(session, get_storage(), item, files, expected_revision)
    return await service.snapshot(session, item, get_storage())


@router.patch("/intakes/{intake_id}/files/{file_id}", response_model=IntakeSnapshot)
async def patch_file(
    intake_id: str,
    file_id: str,
    data: FileUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    item = await editable(session, intake_id, principal)
    await service.update_file(session, item, file_id, data)
    return await service.snapshot(session, item, get_storage())


@router.get("/intakes/{intake_id}/files/{file_id}/download")
async def download(
    intake_id: str,
    file_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    await service.owned(session, intake_id, principal)
    f = await session.get(IntakeFile, file_id)
    if not f or f.intake_id != intake_id:
        raise AppError("not_found", "文件不存在。", 404)
    return Response(
        get_storage().read(f.storage_key),
        media_type=f.mime_type,
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(f.original_filename, safe=""),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/intakes/{intake_id}/messages")
async def messages(
    intake_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    await service.owned(session, intake_id, principal)
    rows = (
        await session.scalars(
            select(IntakeMessage)
            .where(IntakeMessage.intake_id == intake_id)
            .order_by(IntakeMessage.created_at)
        )
    ).all()
    material = await service.files(session, intake_id)
    return [
        {
            k: service.customer_text(m.content, material)
            if k == "content" and m.role == "assistant"
            else getattr(m, k)
            for k in ("id", "role", "content", "status", "file_ids", "job_id", "created_at")
        }
        for m in rows
    ]


@router.post("/intakes/{intake_id}/messages", status_code=202)
async def message(
    intake_id: str,
    data: MessageCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    item = await editable(session, intake_id, principal)
    try:
        m = await service.post_message(session, item, data)
    except IntegrityError:
        await session.rollback()
        m = await session.scalar(
            select(IntakeMessage).where(
                IntakeMessage.intake_id == intake_id,
                IntakeMessage.client_message_id == data.client_message_id,
            )
        )
        if not m:
            raise
    return {"id": m.id, "job_id": m.job_id}


@router.post("/intakes/{intake_id}/prechecks", status_code=202, response_model=JobQueued)
async def precheck(
    intake_id: str,
    data: PrecheckCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    item = await editable(session, intake_id, principal)
    try:
        job = await service.start_precheck(session, item, data.expected_revision)
    except IntegrityError:
        await session.rollback()
        job = await service.latest_precheck(session, intake_id)
        if not job:
            raise
    return {
        "id": job.id,
        "status": job.status,
        "requests_used": job.requests_used,
        "request_limit": job.request_limit,
    }


@router.post("/intakes/{intake_id}/confirm", status_code=201, response_model=ConfirmResult)
async def confirm(
    intake_id: str,
    data: ConfirmCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    item = await editable(session, intake_id, principal)
    return await service.confirm(session, item, data, principal, get_storage())


@router.get("/intakes/{intake_id}/events/stream")
async def events(
    intake_id: str,
    request: Request,
    after_id: int = 0,
    follow: bool = True,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    await service.owned(session, intake_id, principal)
    try:
        cursor = max(after_id, int(request.headers.get("Last-Event-ID", "0")))
    except ValueError:
        raise AppError("invalid_cursor", "事件编号无效。", 422) from None
    sessions = async_sessionmaker(session.bind, expire_on_commit=False)

    async def stream():
        nonlocal cursor
        while True:
            async with sessions() as s:
                rows = (
                    await s.scalars(
                        select(IntakeEvent)
                        .where(IntakeEvent.intake_id == intake_id, IntakeEvent.id > cursor)
                        .order_by(IntakeEvent.id)
                        .limit(100)
                    )
                ).all()
            for e in rows:
                cursor = e.id
                yield f"id: {e.id}\nevent: update\ndata: {json.dumps({'event_type': e.event_type, 'payload': e.payload}, ensure_ascii=False)}\n\n"
            if len(rows) == 100:
                continue
            if not follow or await request.is_disconnected():
                break
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/owner/intakes", response_model=list[IntakeSnapshot])
async def owner_intakes(
    session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)
):
    assert_owner(principal)
    rows = (
        await session.scalars(select(IntakeSession).order_by(IntakeSession.created_at.desc()).limit(100))
    ).all()
    return [await service.snapshot(session, item, get_storage(), owner=True) for item in rows]
