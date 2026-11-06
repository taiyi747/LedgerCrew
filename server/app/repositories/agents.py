from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun, AgentTask, WorkflowEvent


async def task_by_idempotency(session: AsyncSession, order_id: str, key: str) -> AgentTask | None:
    return (await session.scalars(select(AgentTask).where(AgentTask.order_id == order_id,
                                                        AgentTask.idempotency_key == key))).first()


async def task_by_id(session: AsyncSession, task_id: str) -> AgentTask | None:
    return await session.get(AgentTask, task_id)


async def run_by_id(session: AsyncSession, run_id: str) -> AgentRun | None:
    return await session.get(AgentRun, run_id)


async def events_after(session: AsyncSession, order_id: str, after_id: int, limit: int = 100) -> list[WorkflowEvent]:
    return list((await session.scalars(select(WorkflowEvent)
                                       .where(WorkflowEvent.order_id == order_id, WorkflowEvent.id > after_id)
                                       .order_by(WorkflowEvent.id).limit(limit))).all())
