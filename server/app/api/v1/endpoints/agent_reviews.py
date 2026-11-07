from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_current_principal
from app.db.session import get_session
from app.schemas.agent import AgentTaskRead
from app.schemas.agent_review import AgentReviewCreate, AgentReviewRead, AgentReviewStats
from app.services import agent_review_service

router = APIRouter(tags=["agent-reviews"])


@router.get("/agent-tasks/{task_id}/reviews", response_model=list[AgentReviewRead])
async def list_reviews(task_id: str, session: AsyncSession = Depends(get_session),
                       principal: Principal = Depends(get_current_principal)):
    return await agent_review_service.list_reviews(session, task_id, principal)


@router.post("/agent-tasks/{task_id}/reviews", response_model=AgentReviewRead, status_code=201)
async def review_result(task_id: str, data: AgentReviewCreate,
                        session: AsyncSession = Depends(get_session),
                        principal: Principal = Depends(get_current_principal)):
    return await agent_review_service.review_result(session, task_id, data, principal)


@router.post("/agent-tasks/{task_id}/rerun", response_model=AgentTaskRead, status_code=201)
async def rerun_result(task_id: str, idempotency_key: str = Header(alias="Idempotency-Key"),
                       session: AsyncSession = Depends(get_session),
                       principal: Principal = Depends(get_current_principal)):
    return await agent_review_service.rerun_result(session, task_id, idempotency_key, principal)


@router.get("/orders/{order_id}/agent-reviews/stats", response_model=AgentReviewStats)
async def review_stats(order_id: str, session: AsyncSession = Depends(get_session),
                       principal: Principal = Depends(get_current_principal)):
    return await agent_review_service.review_stats(session, order_id, principal)
