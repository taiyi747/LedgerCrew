from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_current_principal
from app.db.session import get_session
from app.schemas.feedback import FeedbackActionCreate, FeedbackActionRead, FeedbackCreate, FeedbackRead
from app.services import feedback_service

router = APIRouter(tags=["feedback"])


@router.post("/studios/{studio_id}/feedback", response_model=FeedbackRead, status_code=201)
async def create_feedback(studio_id: str, data: FeedbackCreate,
                          session: AsyncSession = Depends(get_session),
                          principal: Principal = Depends(get_current_principal)):
    return await feedback_service.create_feedback(session, studio_id, data, principal)


@router.get("/studios/{studio_id}/feedback", response_model=list[FeedbackRead])
async def list_feedback(studio_id: str, session: AsyncSession = Depends(get_session),
                        principal: Principal = Depends(get_current_principal)):
    return await feedback_service.list_feedback(session, studio_id, principal)


@router.get("/feedback/{feedback_id}", response_model=FeedbackRead)
async def get_feedback(feedback_id: str, session: AsyncSession = Depends(get_session),
                       principal: Principal = Depends(get_current_principal)):
    return await feedback_service.get_feedback(session, feedback_id, principal)


@router.get("/feedback/{feedback_id}/actions", response_model=list[FeedbackActionRead])
async def list_actions(feedback_id: str, session: AsyncSession = Depends(get_session),
                       principal: Principal = Depends(get_current_principal)):
    return await feedback_service.list_actions(session, feedback_id, principal)


@router.post("/feedback/{feedback_id}/actions", response_model=FeedbackRead)
async def handle_feedback(feedback_id: str, data: FeedbackActionCreate,
                          session: AsyncSession = Depends(get_session),
                          principal: Principal = Depends(get_current_principal)):
    return await feedback_service.handle_feedback(session, feedback_id, data, principal)
