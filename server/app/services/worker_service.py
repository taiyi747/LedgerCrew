"""SQLite backed worker identity, atomic leases and finite crash recovery."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.types import utc_now
from app.models import AgentTask, AgentTaskHistory, WorkerInstance
from app.services import agent_service


async def register(session: AsyncSession) -> WorkerInstance:
    now = utc_now()
    worker = WorkerInstance(id=str(uuid4()), status="running", started_at=now,
                            last_heartbeat_at=now)
    session.add(worker)
    await session.commit()
    return worker


async def claim_next(session: AsyncSession, worker_id: str) -> tuple[str, int] | None:
    """Compare-and-swap lease; a losing contender never receives the task."""
    worker = await session.get(WorkerInstance, worker_id)
    if worker is None or worker.status != "running":
        raise ValueError("Worker is not active")
    now = utc_now()
    candidates = (await session.scalars(select(AgentTask.id).where(
        AgentTask.status.in_(("queued", "retrying")), AgentTask.lease_owner.is_(None),
        or_(AgentTask.next_attempt_at.is_(None), AgentTask.next_attempt_at <= now))
        .order_by(AgentTask.created_at, AgentTask.id).limit(10))).all()
    for task_id in candidates:
        result = await session.execute(update(AgentTask).where(
            AgentTask.id == task_id, AgentTask.status.in_(("queued", "retrying")),
            AgentTask.lease_owner.is_(None))
            .values(lease_owner=worker_id,
                    lease_expires_at=now + timedelta(seconds=get_settings().worker_lease_seconds),
                    lease_generation=AgentTask.lease_generation + 1,
                    next_attempt_at=None))
        if result.rowcount == 1:
            task = await session.get(AgentTask, task_id)
            worker.current_task_id = task_id
            worker.last_heartbeat_at = now
            session.add(AgentTaskHistory(task_id=task_id, from_status=task.status,
                                         to_status=task.status, reason="lease_claimed"))
            await session.commit()
            return task_id, task.lease_generation
        await session.rollback()
    return None


async def heartbeat(session: AsyncSession, worker_id: str,
                    task_id: str | None = None, generation: int | None = None) -> bool:
    now = utc_now()
    worker = await session.get(WorkerInstance, worker_id)
    if worker is None or worker.status != "running":
        return False
    if task_id is not None:
        renewed = await session.execute(update(AgentTask).where(
            AgentTask.id == task_id, AgentTask.lease_owner == worker_id,
            AgentTask.lease_generation == generation, AgentTask.lease_expires_at > now,
            AgentTask.status.in_(("queued", "retrying", "running")))
            .values(lease_expires_at=now + timedelta(seconds=get_settings().worker_lease_seconds)))
        if renewed.rowcount != 1:
            await session.rollback()
            return False
    worker.last_heartbeat_at = now
    await session.commit()
    return True


async def release(session: AsyncSession, worker_id: str, task_id: str,
                  generation: int) -> bool:
    now = utc_now()
    result = await session.execute(update(AgentTask).where(
        AgentTask.id == task_id, AgentTask.lease_owner == worker_id,
        AgentTask.lease_generation == generation)
        .values(lease_owner=None, lease_expires_at=None))
    worker = await session.get(WorkerInstance, worker_id)
    if worker is not None and worker.current_task_id == task_id:
        worker.current_task_id = None
        worker.last_heartbeat_at = now
    await session.commit()
    return result.rowcount == 1


async def recover_expired(session: AsyncSession) -> list[str]:
    """Fence expired holders before changing task state or scheduling a retry."""
    now = utc_now()
    ids = (await session.scalars(select(AgentTask.id).where(
        AgentTask.lease_owner.is_not(None), AgentTask.lease_expires_at <= now))).all()
    recovered = []
    for task_id in ids:
        task = await session.get(AgentTask, task_id)
        owner = task.lease_owner
        result = await session.execute(update(AgentTask).where(
            AgentTask.id == task_id, AgentTask.lease_owner == owner,
            AgentTask.lease_expires_at <= now)
            .values(lease_owner=None, lease_expires_at=None))
        if result.rowcount != 1:
            await session.rollback()
            continue
        await session.commit()
        await session.refresh(task)
        if task.status == "running":
            await agent_service._transition(session, task.id, {"running"}, "timeout")
            if task.attempt_count < get_settings().worker_max_attempts:
                await agent_service.retry_task(session, task.id)
                task.next_attempt_at = now + timedelta(seconds=min(2 ** task.attempt_count, 60))
                await session.commit()
            else:
                await agent_service._transition(session, task.id, {"timeout"}, "failed",
                                                error="worker_retry_limit")
        else:
            session.add(AgentTaskHistory(task_id=task_id, from_status=task.status,
                                         to_status=task.status, reason="lease_expired_before_start"))
            await session.commit()
        if owner:
            worker = await session.get(WorkerInstance, owner)
            if worker is not None and worker.status == "running":
                worker.status = "lost"
                worker.current_task_id = None
                await session.commit()
        recovered.append(task_id)
    return recovered


async def stop(session: AsyncSession, worker_id: str) -> None:
    worker = await session.get(WorkerInstance, worker_id)
    if worker is None or worker.status == "stopped":
        return
    worker.status = "stopped"
    worker.stopped_at = utc_now()
    worker.current_task_id = None
    await session.commit()


async def retry_if_transient(session: AsyncSession, task_id: str) -> bool:
    task = await session.get(AgentTask, task_id)
    if (task is None or task.status != "failed" or
            task.attempt_count >= get_settings().worker_max_attempts or
            not (task.error_message or "").startswith((
                "agent_invocation_failed: ModelRateLimitError",
                "agent_invocation_failed: ModelServiceUnavailable",
                "agent_invocation_failed: ModelTimeoutError",
                "agent_invocation_failed: ModelNetworkError"))):
        return False
    await agent_service.retry_task(session, task_id)
    task.next_attempt_at = utc_now() + timedelta(seconds=min(2 ** task.attempt_count, 60))
    await session.commit()
    return True


async def abandon(session: AsyncSession, worker_id: str, task_id: str,
                  generation: int) -> None:
    """Graceful interruption marks an owned in-flight task recoverable."""
    task = await session.get(AgentTask, task_id)
    if task is None or task.lease_owner != worker_id or task.lease_generation != generation:
        return
    if task.status == "running":
        await agent_service._transition(session, task_id, {"running"}, "timeout")
        if task.attempt_count < get_settings().worker_max_attempts:
            await agent_service.retry_task(session, task_id)
            task.next_attempt_at = utc_now() + timedelta(seconds=min(2 ** task.attempt_count, 60))
            await session.commit()
    else:
        await release(session, worker_id, task_id, generation)
