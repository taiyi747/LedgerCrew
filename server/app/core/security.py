from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: Literal["customer", "owner"] = "customer"


def get_current_principal(
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Replace this dependency with real authentication before production use."""
    if settings.environment == "production":
        raise AppError("authentication_unavailable", "Production authentication is not configured", 503)
    if not user_id or not user_id.strip() or len(user_id) > 100:
        raise AppError("unauthorized", "X-User-Id is required in development and test", 401)
    identity = user_id.strip()
    return Principal(user_id=identity, role="owner" if identity in settings.dev_owner_user_ids else "customer")


def assert_owner(principal: Principal) -> None:
    if principal.role != "owner":
        raise AppError("forbidden", "Owner role is required", 403)
