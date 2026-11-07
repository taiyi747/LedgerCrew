from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import Principal, assert_owner, get_current_principal
from app.db.session import get_session
from app.models import AgentTask, AgentTaskHistory
from app.schemas.agent import AgentTaskHistoryRead, AgentTaskRead
from app.services import agent_service
from app.services.access import order_for_user

router = APIRouter(tags=["worker-tasks"])


async def _authorized_task(session: AsyncSession, task_id: str, principal: Principal) -> AgentTask:
    assert_owner(principal)
    task = await session.get(AgentTask, task_id)
    if task is None:
        raise AppError("not_found", "Agent task not found", 404)
    await order_for_user(session, task.order_id, principal)
    return task


@router.get("/agent-tasks/{task_id}", response_model=AgentTaskRead)
async def get_task(task_id: str, session: AsyncSession = Depends(get_session),
                   principal: Principal = Depends(get_current_principal)):
    return await _authorized_task(session, task_id, principal)


@router.get("/agent-tasks/{task_id}/history", response_model=list[AgentTaskHistoryRead])
async def task_history(task_id: str, session: AsyncSession = Depends(get_session),
                       principal: Principal = Depends(get_current_principal)):
    await _authorized_task(session, task_id, principal)
    return list((await session.scalars(select(AgentTaskHistory).where(AgentTaskHistory.task_id == task_id)
                                       .order_by(AgentTaskHistory.id))).all())


@router.post("/agent-tasks/{task_id}/cancel", response_model=AgentTaskRead)
async def cancel_task(task_id: str, session: AsyncSession = Depends(get_session),
                      principal: Principal = Depends(get_current_principal)):
    await _authorized_task(session, task_id, principal)
    return await agent_service.cancel_task(session, task_id)


@router.post("/agent-tasks/{task_id}/retry", response_model=AgentTaskRead)
async def retry_task(task_id: str, session: AsyncSession = Depends(get_session),
                     principal: Principal = Depends(get_current_principal)):
    await _authorized_task(session, task_id, principal)
    return await agent_service.retry_task(session, task_id)
