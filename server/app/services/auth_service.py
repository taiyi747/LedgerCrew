"""认证业务协调（v0.2）。

只做与具体身份服务无关的编排：统一错误响应、身份回读、认证状态撤销。
凭据签发/解析/撤销全部委托 ``IdentityProvider``（见 ``app/core/security.py``）。
"""


from app.core.exceptions import AppError
from app.core.security import AuthContext, AuthSession, IdentityProvider
from app.schemas.auth import AuthCredential, AuthUser, LoginRequest, LoginResponse, LogoutResponse

# 登录失败的统一响应：不区分"邮箱未注册/密码错误/提供者拒绝"，避免账号枚举
INVALID_CREDENTIALS_MESSAGE = "Invalid email or password"
NOT_AUTHENTICATED_MESSAGE = "Authentication required"


async def login(provider: IdentityProvider, request: LoginRequest) -> LoginResponse:
    session: AuthSession | None = await provider.login(request.login_name, request.password)
    if session is None:
        raise AppError("unauthorized", INVALID_CREDENTIALS_MESSAGE, 401)
    return LoginResponse(
        user=AuthUser(user_id=session.identity.user_id, email=session.identity.email),
        credential=AuthCredential(scheme=session.scheme, value=session.credential, expires_at=session.expires_at),
    )


async def logout(provider: IdentityProvider, context: AuthContext) -> LogoutResponse:
    revoked = await provider.logout(context.scheme, context.credential)
    if not revoked:
        # 无效或过期的认证状态不能"假成功"：未执行撤销即报统一错误
        raise AppError("unauthorized", NOT_AUTHENTICATED_MESSAGE, 401)
    return LogoutResponse(status="logged_out")


async def current_user(context: AuthContext) -> AuthUser:
    return AuthUser(user_id=context.identity.user_id, email=context.identity.email)
