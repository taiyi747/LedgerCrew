from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core.security import account_role, session_user
from app.db.session import get_session
from app.schemas.auth import AccountRead, LoginRequest, RegisterRequest, TrialRead, TrialRequestCreate
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_session(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        auth_service.SESSION_COOKIE_NAME,
        token,
        max_age=int(auth_service.SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        path="/",
    )


@router.post("/register", response_model=AccountRead, status_code=201)
async def register(
    data: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    user = await auth_service.register(session, data.username, data.password, data.confirm_password)
    _issue_session(response, await auth_service.create_session(session, user), settings)
    return AccountRead(id=user.id, username=user.username, role=account_role(user, settings))


@router.post("/login", response_model=AccountRead)
async def login(
    data: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    user = await auth_service.login(session, data.username, data.password)
    _issue_session(response, await auth_service.create_session(session, user), settings)
    return AccountRead(id=user.id, username=user.username, role=account_role(user, settings))


@router.get("/me", response_model=AccountRead)
async def me(request: Request, session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)):
    user = await session_user(request, session)
    if user is None:
        raise AppError("unauthorized", "未登录", 401)
    return AccountRead(id=user.id, username=user.username, role=account_role(user, settings))


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    token = request.cookies.get(auth_service.SESSION_COOKIE_NAME)
    if token:
        await auth_service.revoke_session(session, token)
    response.delete_cookie(auth_service.SESSION_COOKIE_NAME, path="/")


@router.post("/trial", response_model=TrialRead, status_code=201)
async def trial(
    data: TrialRequestCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = await session_user(request, session)
    if user is None:
        raise AppError("unauthorized", "请先登录后再开启免费体验", 401)
    order = await auth_service.start_trial(session, user, data.request_id)
    return TrialRead(
        order_no=order.order_no,
        user_id=user.id,
        username=user.username,
        plan_id="FREE",
        plan_name="免费体验",
        amount_cents=order.price_cents or 0,
        payment_status="not_required",
        status="pending",
        created_at=order.created_at,
    )
