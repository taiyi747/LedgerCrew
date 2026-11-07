"""认证接口的 Pydantic 2 线协议（v0.2 候选契约）。

DEC-013（生产认证与角色）当前为 pending：本模块只定义与具体身份服务无关的
请求/响应形状，不包含 Token、Session、OAuth、角色或租户权限字段。
凭据（AuthCredential）是"提供者定义的不透明认证状态"，其语义、格式和生命周期
由最终确认的身份服务决定；开发环境模拟值不代表任何生产机制。
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

# 保守的邮箱格式校验（不引入新依赖）；生产身份服务确认后可替换为其正式规则。
EMAIL_PATTERN = r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"

_MAX_EMAIL_LENGTH = 254
_MAX_PASSWORD_LENGTH = 512


class LoginRequest(BaseModel):
    """登录请求。密码用 SecretStr 承载，repr/日志不出现明文。"""

    model_config = ConfigDict(extra="forbid")

    email: Annotated[str, Field(pattern=EMAIL_PATTERN, max_length=_MAX_EMAIL_LENGTH)]
    password: SecretStr

    @field_validator("password")
    @classmethod
    def password_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not raw.strip() or len(raw) > _MAX_PASSWORD_LENGTH:
            raise ValueError("password is required")
        return value


class AuthUser(BaseModel):
    """经后端验证的身份信息。不含角色/租户字段（待 DEC-013）。"""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=1, max_length=_MAX_EMAIL_LENGTH)


class AuthCredential(BaseModel):
    """提供者定义的不透明认证状态。

    ``scheme`` 与 ``value`` 的格式由身份服务决定；``expires_at`` 为 UTC 过期时间，
    ``None`` 表示提供者未声明过期（不代表永久有效）。
    """

    model_config = ConfigDict(extra="forbid")

    scheme: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=2000)
    expires_at: datetime | None = None


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: AuthUser
    credential: AuthCredential


class LogoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["logged_out"]
