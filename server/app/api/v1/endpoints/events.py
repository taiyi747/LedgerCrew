import asyncio
import time

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.background import BackgroundTask

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core.security import Principal, get_current_principal
from app.db.session import get_session
from app.repositories import agents as repo
from app.schemas.agent import WorkflowEventRead
from app.services.access import order_for_user

router = APIRouter(prefix="/orders/{order_id}/events", tags=["events"])


@router.get("/stream")
async def stream_events(
    order_id: str, request: Request, after_id: int | None = Query(default=None, ge=0),
    follow: bool = True, last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    await order_for_user(session, order_id, principal)
    if after_id is None:
        try:
            cursor = int(last_event_id) if last_event_id is not None else 0
        except ValueError as exc:
            raise AppError("invalid_event_cursor", "Last-Event-ID must be a nonnegative integer", 422) from exc
        if cursor < 0:
            raise AppError("invalid_event_cursor", "Last-Event-ID must be a nonnegative integer", 422)
    else:
        cursor = after_id
    if session.bind is None:
        raise RuntimeError("SSE requires a bound database session")
    sessions = async_sessionmaker(session.bind, expire_on_commit=False)
    limiter = request.app.state.sse_connection_limiter
    if not await limiter.acquire(settings.sse_max_connections):
        raise AppError("sse_capacity", "Too many event streams", 429)

    async def events():
        nonlocal cursor
        last_heartbeat = time.monotonic()
        while True:
            async with sessions() as poll_session:
                batch = await repo.events_after(poll_session, order_id, cursor)
            for event in batch:
                cursor = event.id
                payload = WorkflowEventRead(
                    event_id=event.id, order_id=event.order_id, run_id=event.run_id,
                    task_id=event.task_id, event_type=event.event_type,
                    payload=event.payload, created_at=event.created_at,
                )
                yield f"id: {event.id}\nevent: {event.event_type}\ndata: {payload.model_dump_json()}\n\n"
            if len(batch) == 100:
                continue
            if not follow or await request.is_disconnected():
                break
            if time.monotonic() - last_heartbeat >= settings.sse_heartbeat_seconds:
                yield ": keep-alive\n\n"
                last_heartbeat = time.monotonic()
            await asyncio.sleep(settings.sse_poll_seconds)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                             background=BackgroundTask(limiter.release))
