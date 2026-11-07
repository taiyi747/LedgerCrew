from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.db.session import get_session
from app.models import User
from app.services import auth_service


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: Literal["customer", "owner"] = "customer"


async def session_user(request: Request, session: AsyncSession) -> User | None:
    """Resolve the account behind the HttpOnly session cookie, if any."""
    token = request.cookies.get(auth_service.SESSION_COOKIE_NAME)
    if not token:
        return None
    return await auth_service.user_for_token(session, token)


def account_role(account: User, settings: Settings) -> Literal["customer", "owner"]:
    """Administrator accounts are listed in DEV_OWNER_USER_IDS by id or username."""
    listed = settings.dev_owner_user_ids
    admin = settings.admin_username.strip().casefold()
    return "owner" if account.id in listed or account.username_key in listed or account.username_key == admin else "customer"


async def get_current_principal(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Cookie session first; the X-User-Id header stays for local development.

    The header path is refused in production, so a real deployment can only be
    reached with a signed-in account (or the owner console, which still relies
    on the development identity until real authentication is configured).
    """
    account = await session_user(request, session)
    if account is not None:
        return Principal(user_id=account.id, role=account_role(account, settings))
    if settings.environment == "production":
        raise AppError("authentication_unavailable", "Sign-in is required in production", 503)
    if not user_id or not user_id.strip() or len(user_id) > 100:
        raise AppError("unauthorized", "Sign in, or send X-User-Id in development", 401)
    identity = user_id.strip()
    return Principal(user_id=identity, role="owner" if identity in settings.dev_owner_user_ids else "customer")


def assert_owner(principal: Principal) -> None:
    if principal.role != "owner":
        raise AppError("forbidden", "Owner role is required", 403)
