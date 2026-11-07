"""认证 HTTP 路由（v0.2）。

状态标注（DEC-013 pending）：

- ``POST /api/v1/auth/login``、``POST /api/v1/auth/logout``、``GET /api/v1/auth/me``
  为 **implemented**：已实现并挂载，但仅在开发/测试环境 **enabled**；
  生产环境统一由安全门禁返回 503 ``authentication_unavailable``。
- ``POST /api/v1/auth/refresh`` 为 **proposed**：依赖最终认证机制，
  DEC-013 确认前不实现、不挂载（见 contracts/API.md 与 contracts/openapi.json）。
"""

from fastapi import APIRouter, Depends, Response

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core.security import AuthContext, IdentityProvider, get_identity_provider, require_auth_context
from app.schemas.auth import AuthUser, LoginRequest, LoginResponse, LogoutResponse
from app.services import auth_service
from app.services.local_auth import LocalIdentityProvider

router = APIRouter(prefix="/auth", tags=["auth"])

_UNAUTHORIZED = {"description": "unauthorized"}
_UNAVAILABLE = {"description": "authentication_unavailable (production gate)"}


@router.post(
    "/login",
    response_model=LoginResponse,
    response_model_exclude_none=True,
    responses={401: _UNAUTHORIZED, 503: _UNAVAILABLE},
    summary="用户登录（开发/测试环境启用；生产 503，DEC-013 pending）",
)
async def login(data: LoginRequest, response: Response,
                provider: IdentityProvider = Depends(get_identity_provider),
                settings: Settings = Depends(get_settings)) -> LoginResponse:
    if settings.environment == "production":
        if not isinstance(provider, LocalIdentityProvider):
            raise AppError("authentication_unavailable", "Production authentication is not configured", 503)
        session = await provider.login(data.login_name, data.password)
        if session is None:
            raise AppError("unauthorized", auth_service.INVALID_CREDENTIALS_MESSAGE, 401)
        response.set_cookie("lc_session", session.credential, max_age=settings.auth_session_ttl_seconds,
                            httponly=True, secure=True, samesite="lax", path="/")
        response.set_cookie("lc_csrf", session.csrf_token, max_age=settings.auth_session_ttl_seconds,
                            httponly=False, secure=True, samesite="lax", path="/")
        return LoginResponse(user=AuthUser(user_id=session.identity.user_id,
                                           username=session.identity.username))
    return await auth_service.login(provider, data)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    responses={401: _UNAUTHORIZED, 503: _UNAVAILABLE},
    summary="退出登录（撤销认证状态；开发/测试环境启用，生产 503）",
)
async def logout(
    response: Response,
    provider: IdentityProvider = Depends(get_identity_provider),
    context: AuthContext = Depends(require_auth_context),
) -> LogoutResponse:
    result = await auth_service.logout(provider, context)
    if isinstance(provider, LocalIdentityProvider):
        response.delete_cookie("lc_session", path="/")
        response.delete_cookie("lc_csrf", path="/")
    return result


@router.get(
    "/me",
    response_model=AuthUser,
    response_model_exclude_none=True,
    responses={401: _UNAUTHORIZED, 503: _UNAVAILABLE},
    summary="获取当前用户（服务端验证的身份；开发/测试环境启用，生产 503）",
)
async def me(context: AuthContext = Depends(require_auth_context)) -> AuthUser:
    if context.identity.username is not None:
        return AuthUser(user_id=context.identity.user_id, username=context.identity.username)
    return await auth_service.current_user(context)
