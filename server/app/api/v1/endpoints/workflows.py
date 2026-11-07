"""Create and review a full MAF workflow through authenticated backend state."""

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_current_principal
from app.db.session import get_session
from app.schemas.agent import AgentTaskRead
from app.schemas.workflow import WorkflowReplyCreate
from app.services import workflow_service

router = APIRouter(tags=["workflows"])


@router.post("/orders/{order_id}/workflows", response_model=AgentTaskRead, status_code=201)
async def create_workflow(order_id: str, idempotency_key: str = Header(alias="Idempotency-Key"),
                          session: AsyncSession = Depends(get_session),
                          principal: Principal = Depends(get_current_principal)):
    return await workflow_service.create(session, order_id, idempotency_key, principal)


@router.get("/agent-tasks/{task_id}/workflow-review")
async def pending_workflow_review(task_id: str, session: AsyncSession = Depends(get_session),
                                  principal: Principal = Depends(get_current_principal)):
    return await workflow_service.pending_review(session, task_id, principal)


@router.post("/agent-tasks/{task_id}/workflow-reply", response_model=AgentTaskRead)
async def reply_to_workflow(task_id: str, data: WorkflowReplyCreate,
                            session: AsyncSession = Depends(get_session),
                            principal: Principal = Depends(get_current_principal)):
    return await workflow_service.submit_reply(session, task_id, data, principal)
