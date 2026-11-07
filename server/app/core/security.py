"""身份与认证抽象（v0.2）。

DEC-013（生产身份服务、角色映射、租户授权）当前为 pending：

- 生产环境一律走 ``UnconfiguredIdentityProvider``，任何认证操作都返回 503
  ``authentication_unavailable``，保持 MVP 的生产安全门禁，不伪造认证能力；
- 开发/测试环境使用 ``DevSimulatedIdentityProvider``（进程内模拟凭据），
  仅是开发适配，禁止用于生产；
- 业务代码只依赖 ``IdentityProvider`` 协议，与具体身份服务（JWT/OAuth/Session
  等）解耦，最终机制由已确认的身份服务决定。

MVP 兼容：``Principal``、``get_current_principal``、``assert_owner`` 保持原有
行为；无 ``Authorization`` 头时仍走 ``X-User-Id`` 开发模拟（原有测试不受影响）。
"""

import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from fastapi import Depends, Header
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError

DEV_SESSION_SCHEME = "DevSession"


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: Literal["customer", "owner"] = "customer"


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """后端验证过的身份；永远由服务端解析，不信任客户端自报的 user_id。"""

    user_id: str
    email: str


@dataclass(frozen=True)
class AuthSession:
    """一次认证签发的不透明认证状态（形状中立，不预设 Token/Session 机制）。"""

    scheme: str
    credential: str
    expires_at: datetime | None
    identity: AuthenticatedIdentity


class IdentityProvider(Protocol):
    """认证提供者接口。生产实现由 DEC-013 确认后接入。"""

    async def login(self, email: str, password: SecretStr) -> AuthSession | None:
        """认证并签发认证状态；失败返回 ``None``（调用方必须给出统一错误）。"""

    async def resolve(self, scheme: str, credential: str) -> AuthenticatedIdentity | None:
        """解析认证状态；无效、伪造或过期返回 ``None``。"""

    async def logout(self, scheme: str, credential: str) -> bool:
        """撤销认证状态；返回是否确实撤销了有效状态。"""


class UnconfiguredIdentityProvider:
    """生产环境占位提供者：DEC-013 确认前不提供任何认证能力。"""

    def _blocked(self) -> None:
        raise AppError("authentication_unavailable", "Production authentication is not configured", 503)

    async def login(self, email: str, password: SecretStr) -> AuthSession | None:
        self._blocked()

    async def resolve(self, scheme: str, credential: str) -> AuthenticatedIdentity | None:
        self._blocked()

    async def logout(self, scheme: str, credential: str) -> bool:
        self._blocked()


@dataclass
class _DevSession:
    identity: AuthenticatedIdentity
    expires_at: datetime


class DevSimulatedIdentityProvider:
    """开发/测试模拟认证提供者（严禁生产使用）。

    仅在非生产环境构造；凭据是进程内的不透明句柄，不代表任何生产 Token/Session
    机制。同一账号重复登录会替换旧凭据（防重复提交导致凭据堆积）。
    """

    def __init__(
        self,
        settings: Settings,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if settings.environment == "production":
            raise RuntimeError("DevSimulatedIdentityProvider must never be used in production")
        self._accounts = {account.email.lower(): account for account in settings.dev_auth_accounts}
        self._ttl = timedelta(seconds=settings.dev_auth_credential_ttl_seconds)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sessions: dict[str, _DevSession] = {}

    async def login(self, email: str, password: SecretStr) -> AuthSession | None:
        account = self._accounts.get(email.lower())
        expected = (account.password.get_secret_value() if account else "").encode("utf-8")
        provided = password.get_secret_value().encode("utf-8")
        # 统一失败路径 + 均等化比较：不区分"邮箱未注册"与"密码错误"
        matched = hmac.compare_digest(expected, provided) and account is not None
        if not matched or account is None:
            return None
        self._prune_expired()
        identity = AuthenticatedIdentity(user_id=account.user_id, email=account.email)
        for value, session in list(self._sessions.items()):
            if session.identity.user_id == identity.user_id:
                del self._sessions[value]
        credential = secrets.token_urlsafe(32)
        expires_at = self._clock() + self._ttl
        self._sessions[credential] = _DevSession(identity=identity, expires_at=expires_at)
        return AuthSession(scheme=DEV_SESSION_SCHEME, credential=credential, expires_at=expires_at, identity=identity)

    async def resolve(self, scheme: str, credential: str) -> AuthenticatedIdentity | None:
        if scheme.lower() != DEV_SESSION_SCHEME.lower():
            return None
        self._prune_expired()
        session = self._sessions.get(credential)
        return session.identity if session else None

    async def logout(self, scheme: str, credential: str) -> bool:
        if scheme.lower() != DEV_SESSION_SCHEME.lower():
            return False
        self._prune_expired()
        return self._sessions.pop(credential, None) is not None

    def _prune_expired(self) -> None:
        now = self._clock()
        for value in [value for value, session in self._sessions.items() if session.expires_at <= now]:
            del self._sessions[value]


_provider_cache: tuple[Settings, IdentityProvider] | None = None


def get_identity_provider(settings: Settings = Depends(get_settings)) -> IdentityProvider:
    """按环境选择认证提供者：生产为 503 门禁占位，其余为开发模拟。"""
    global _provider_cache
    if settings.environment == "production":
        return UnconfiguredIdentityProvider()
    if _provider_cache is not None and _provider_cache[0] is settings:
        return _provider_cache[1]
    _provider_cache = (settings, DevSimulatedIdentityProvider(settings))
    return _provider_cache[1]


def reset_identity_provider_cache() -> None:
    """测试辅助：Settings 重建后清空提供者缓存。"""
    global _provider_cache
    _provider_cache = None


def _parse_authorization(header: str) -> tuple[str, str] | None:
    parts = header.strip().split(None, 1)
    if len(parts) != 2 or not parts[0] or not parts[1].strip():
        return None
    return parts[0], parts[1].strip()


@dataclass(frozen=True)
class AuthContext:
    """已认证请求上下文：身份 + 用于撤销的原始认证状态。"""

    identity: AuthenticatedIdentity
    scheme: str
    credential: str


async def require_auth_context(
    authorization: str | None = Header(default=None),
    provider: IdentityProvider = Depends(get_identity_provider),
) -> AuthContext:
    """认证依赖：解析 ``Authorization: <scheme> <value>``。

    缺失、格式非法、伪造或过期一律 401 ``unauthorized``（统一响应，不做区分）；
    生产环境由占位提供者直接返回 503，安全门禁优先于一切。
    """
    parsed = _parse_authorization(authorization) if authorization else None
    scheme, credential = parsed if parsed else ("", "")
    identity = await provider.resolve(scheme, credential)
    if identity is None:
        raise AppError("unauthorized", "Authentication required", 401)
    return AuthContext(identity=identity, scheme=scheme, credential=credential)


async def get_current_principal(
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    authorization: str | None = Header(default=None),
    provider: IdentityProvider = Depends(get_identity_provider),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """MVP 身份依赖（保持兼容）。

    - 生产：503 ``authentication_unavailable``（原有安全门禁，未改变）；
    - 非生产且带 ``Authorization``：凭认证状态解析服务端身份（不信任 X-User-Id）；
    - 非生产且无 ``Authorization``：原样走 ``X-User-Id`` 开发模拟（MVP 行为不变）。
    """
    if settings.environment == "production":
        raise AppError("authentication_unavailable", "Production authentication is not configured", 503)
    if authorization is not None:
        parsed = _parse_authorization(authorization)
        identity = await provider.resolve(*parsed) if parsed else None
        if identity is None:
            raise AppError("unauthorized", "Authentication required", 401)
        return Principal(user_id=identity.user_id, role=_role_for(identity.user_id, settings))
    if not user_id or not user_id.strip() or len(user_id) > 100:
        raise AppError("unauthorized", "X-User-Id is required in development and test", 401)
    identity = user_id.strip()
    return Principal(user_id=identity, role=_role_for(identity, settings))


def _role_for(user_id: str, settings: Settings) -> Literal["customer", "owner"]:
    return "owner" if user_id in settings.dev_owner_user_ids else "customer"


def assert_owner(principal: Principal) -> None:
    if principal.role != "owner":
        raise AppError("forbidden", "Owner role is required", 403)
