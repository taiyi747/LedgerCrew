"""认证 HTTP 路由（v0.2）。

状态标注（DEC-013 pending）：

- ``POST /api/v1/auth/login``、``POST /api/v1/auth/logout``、``GET /api/v1/auth/me``
  为 **implemented**：已实现并挂载，但仅在开发/测试环境 **enabled**；
  生产环境统一由安全门禁返回 503 ``authentication_unavailable``。
- ``POST /api/v1/auth/refresh`` 为 **proposed**：依赖最终认证机制，
  DEC-013 确认前不实现、不挂载（见 contracts/API.md 与 contracts/openapi.json）。
"""

from fastapi import APIRouter, Depends

from app.core.security import AuthContext, IdentityProvider, get_identity_provider, require_auth_context
from app.schemas.auth import AuthUser, LoginRequest, LoginResponse, LogoutResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

_UNAUTHORIZED = {"description": "unauthorized"}
_UNAVAILABLE = {"description": "authentication_unavailable (production gate)"}


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={401: _UNAUTHORIZED, 503: _UNAVAILABLE},
    summary="用户登录（开发/测试环境启用；生产 503，DEC-013 pending）",
)
async def login(data: LoginRequest, provider: IdentityProvider = Depends(get_identity_provider)) -> LoginResponse:
    return await auth_service.login(provider, data)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    responses={401: _UNAUTHORIZED, 503: _UNAVAILABLE},
    summary="退出登录（撤销认证状态；开发/测试环境启用，生产 503）",
)
async def logout(
    provider: IdentityProvider = Depends(get_identity_provider),
    context: AuthContext = Depends(require_auth_context),
) -> LogoutResponse:
    return await auth_service.logout(provider, context)


@router.get(
    "/me",
    response_model=AuthUser,
    responses={401: _UNAUTHORIZED, 503: _UNAVAILABLE},
    summary="获取当前用户（服务端验证的身份；开发/测试环境启用，生产 503）",
)
async def me(context: AuthContext = Depends(require_auth_context)) -> AuthUser:
    return await auth_service.current_user(context)
