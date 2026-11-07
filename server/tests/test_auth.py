"""v0.2 认证接口测试（DEC-013 pending）。

覆盖：登录参数校验、邮箱格式校验、密码缺失、认证失败统一响应、未认证/已认证访问
/me、退出登录、过期认证状态、非法身份信息、开发模拟认证、生产 503 安全门禁、
MVP 权限回归。测试使用 FakeIdentityProvider 测试替身，不依赖任何真实第三方身份服务。
"""

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker

from alembic import command
from app.core.config import Settings, get_settings
from app.core.security import (
    AuthenticatedIdentity,
    AuthSession,
    DevSimulatedIdentityProvider,
    get_identity_provider,
    reset_identity_provider_cache,
)
from app.db.session import get_session, make_engine
from app.main import app
from app.models import UserSession
from app.services.local_auth import SCHEME, LocalIdentityProvider, create_user

LOGIN = "/api/v1/auth/login"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "example-password"
DEMO_HEADERS = {"Authorization": "DevSession placeholder"}


class FakeIdentityProvider:
    """测试替身：进程内假身份服务，任何请求都不触达真实第三方服务。"""

    scheme = "FakeAuth"

    def __init__(self) -> None:
        self.sessions: dict[str, AuthenticatedIdentity] = {}
        self.expired: set[str] = set()
        self.revoked: list[str] = []
        self.login_attempts = 0

    async def login(self, email: str, password: SecretStr) -> AuthSession | None:
        self.login_attempts += 1
        if email != "fake@example.com" or password.get_secret_value() != "fake-password":
            return None
        credential = f"fake-credential-{self.login_attempts}"
        identity = AuthenticatedIdentity(user_id="fake-user", email="fake@example.com")
        self.sessions[credential] = identity
        expires_at = datetime.now(UTC) + timedelta(minutes=5)
        return AuthSession(scheme=self.scheme, credential=credential, expires_at=expires_at, identity=identity)

    async def resolve(self, scheme: str, credential: str) -> AuthenticatedIdentity | None:
        if scheme.lower() != self.scheme.lower() or credential in self.expired:
            return None
        return self.sessions.get(credential)

    async def logout(self, scheme: str, credential: str) -> bool:
        self.revoked.append(credential)
        return self.sessions.pop(credential, None) is not None


def serve(tmp_path: Path, monkeypatch, scenario, *, environment: str = "test", provider=None, env=None,
          db: bool = False, seed_users=None) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    if db:
        db_path = tmp_path / f"auth-{uuid4().hex}.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
        get_settings.cache_clear()
        config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
        command.upgrade(config, "head")
    get_settings.cache_clear()
    reset_identity_provider_cache()
    if provider is not None:
        app.dependency_overrides[get_identity_provider] = lambda: provider

    async def run() -> None:
        engine = make_engine(get_settings().database_url) if db else None
        try:
            if engine is not None:
                sessions = async_sessionmaker(engine, expire_on_commit=False)

                async def session_override():
                    async with sessions() as session:
                        yield session

                app.dependency_overrides[get_session] = session_override
                for username, password, role in seed_users or []:
                    async with sessions() as session:
                        await create_user(session, username, password, role)
            async with AsyncClient(transport=ASGITransport(app=app),
                                   base_url="https://test" if environment == "production" else "http://test") as client:
                await scenario(client)
        finally:
            if engine is not None:
                await engine.dispose()

    try:
        asyncio.run(run())
    finally:
        app.dependency_overrides.clear()
        reset_identity_provider_cache()
        get_settings.cache_clear()


async def login_ok(client: AsyncClient, email: str = DEMO_EMAIL, password: str = DEMO_PASSWORD) -> dict:
    response = await client.post(LOGIN, json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()


def auth_header(credential: str, scheme: str = "DevSession") -> dict[str, str]:
    return {"Authorization": f"{scheme} {credential}"}


# 1. 登录请求参数校验


def test_login_request_validation(tmp_path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        for body in (
            {},
            {"email": DEMO_EMAIL},
            {"email": 123, "password": DEMO_PASSWORD},
            {"email": DEMO_EMAIL, "password": 123},
            {"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "role": "admin"},
        ):
            response = await client.post(LOGIN, json=body)
            assert response.status_code == 422
            assert response.json() == {"error": {"code": "validation_error", "message": "Invalid request"}}

    serve(tmp_path, monkeypatch, scenario)


# 2. 邮箱格式校验


def test_login_email_format_is_validated(tmp_path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        for bad in ("not-an-email", "demo@example", "a b@c.com", "demo@.com", "", "demo@exam ple.com"):
            response = await client.post(LOGIN, json={"email": bad, "password": DEMO_PASSWORD})
            assert response.status_code == 422, bad
            assert response.json()["error"]["code"] == "validation_error"

    serve(tmp_path, monkeypatch, scenario)


# 3. 密码缺失


def test_login_password_is_required(tmp_path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        for body in (
            {"email": DEMO_EMAIL},
            {"email": DEMO_EMAIL, "password": None},
            {"email": DEMO_EMAIL, "password": ""},
            {"email": DEMO_EMAIL, "password": "   "},
        ):
            response = await client.post(LOGIN, json=body)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "validation_error"

    serve(tmp_path, monkeypatch, scenario)


# 4. 认证失败（统一错误、不泄露注册状态、不进日志）


def test_login_failure_is_uniform_and_leaks_nothing(tmp_path, monkeypatch, caplog) -> None:
    async def scenario(client: AsyncClient) -> None:
        wrong_password = await client.post(LOGIN, json={"email": DEMO_EMAIL, "password": "wrong-password"})
        unknown_email = await client.post(LOGIN, json={"email": "nobody@example.com", "password": DEMO_PASSWORD})
        assert wrong_password.status_code == 401
        assert unknown_email.status_code == 401
        # 统一错误响应：不区分"密码错误"与"邮箱未注册"，防止账号枚举
        assert wrong_password.json() == unknown_email.json()
        assert wrong_password.json() == {"error": {"code": "unauthorized", "message": "Invalid email or password"}}
        assert "nobody@example.com" not in wrong_password.text
        assert "nobody@example.com" not in unknown_email.text

    caplog.set_level(logging.DEBUG)
    serve(tmp_path, monkeypatch, scenario)
    assert DEMO_PASSWORD not in caplog.text
    assert "wrong-password" not in caplog.text


# 5. 未认证访问 /me


def test_me_without_authentication_returns_401(tmp_path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        for headers in (None, DEMO_HEADERS, {"Authorization": ""}):
            response = await client.get(ME, headers=headers)
            assert response.status_code == 401
            assert response.json() == {"error": {"code": "unauthorized", "message": "Authentication required"}}

    serve(tmp_path, monkeypatch, scenario)


# 6. 已认证访问 /me（服务端验证身份，不信任客户端自报 user_id）


def test_me_returns_server_verified_identity(tmp_path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        body = await login_ok(client)
        assert body["user"] == {"user_id": "demo", "email": DEMO_EMAIL}
        credential = body["credential"]
        assert credential["scheme"] == "DevSession"
        assert credential["value"] and credential["expires_at"]

        me = await client.get(ME, headers=auth_header(credential["value"]))
        assert me.status_code == 200
        assert me.json() == {"user_id": "demo", "email": DEMO_EMAIL}

        # 伪造的 X-User-Id 不能改变身份；/me 只认服务端解析的认证状态
        forged = await client.get(ME, headers={**auth_header(credential["value"]), "X-User-Id": "attacker"})
        assert forged.status_code == 200
        assert forged.json()["user_id"] == "demo"

    serve(tmp_path, monkeypatch, scenario)


# 7. 退出登录（真实撤销认证状态）


def test_logout_revokes_auth_state(tmp_path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        body = await login_ok(client)
        headers = auth_header(body["credential"]["value"])

        logout = await client.post(LOGOUT, headers=headers)
        assert logout.status_code == 200
        assert logout.json() == {"status": "logged_out"}

        after = await client.get(ME, headers=headers)
        assert after.status_code == 401

        again = await client.post(LOGOUT, headers=headers)
        assert again.status_code == 401
        assert again.json() == {"error": {"code": "unauthorized", "message": "Authentication required"}}

    serve(tmp_path, monkeypatch, scenario)


# 8. 过期认证状态


def test_expired_auth_state_is_rejected(tmp_path, monkeypatch) -> None:
    provider = FakeIdentityProvider()

    async def scenario(client: AsyncClient) -> None:
        response = await client.post(LOGIN, json={"email": "fake@example.com", "password": "fake-password"})
        body = response.json()
        headers = auth_header(body["credential"]["value"], scheme=provider.scheme)
        assert (await client.get(ME, headers=headers)).status_code == 200

        provider.expired.add(body["credential"]["value"])
        assert (await client.get(ME, headers=headers)).status_code == 401
        expired_logout = await client.post(LOGOUT, headers=headers)
        assert expired_logout.status_code == 401
        assert expired_logout.json()["error"]["code"] == "unauthorized"

    serve(tmp_path, monkeypatch, scenario, provider=provider)


def test_dev_provider_expires_and_replaces_credentials() -> None:
    settings = Settings(environment="test")
    start = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)
    clock_state = {"now": start}
    provider = DevSimulatedIdentityProvider(settings, clock=lambda: clock_state["now"])

    async def check() -> None:
        first = await provider.login(DEMO_EMAIL, SecretStr(DEMO_PASSWORD))
        assert first is not None
        second = await provider.login(DEMO_EMAIL, SecretStr(DEMO_PASSWORD))
        assert second is not None and second.credential != first.credential
        # 防重复提交：重复登录后旧凭据立即失效，不堆积有效认证状态
        assert await provider.resolve(first.scheme, first.credential) is None
        assert await provider.resolve(second.scheme, second.credential) is not None
        # 过期后不可解析、退出登录不能"假成功"
        clock_state["now"] = start + timedelta(seconds=3601)
        assert await provider.resolve(second.scheme, second.credential) is None
        assert await provider.logout(second.scheme, second.credential) is False

    asyncio.run(check())


# 9. 非法身份信息


def test_invalid_identity_information_is_rejected(tmp_path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        body = await login_ok(client)
        credential = body["credential"]["value"]
        cases = (
            {"Authorization": "garbage"},
            {"Authorization": "DevSession"},
            {"Authorization": "DevSession "},
            {"Authorization": f"Bearer {credential}"},
            {"Authorization": "DevSession forged-credential"},
            {"Authorization": "DevSession " + "x" * 120},
            {"Authorization": "notascheme value extra"},
        )
        for headers in cases:
            response = await client.get(ME, headers=headers)
            assert response.status_code == 401, headers
            assert response.json() == {"error": {"code": "unauthorized", "message": "Authentication required"}}

    serve(tmp_path, monkeypatch, scenario)


def test_invalid_credential_grants_no_business_access(tmp_path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        for headers in ({"Authorization": "DevSession forged"}, {"X-User-Id": ""}):
            response = await client.get("/api/v1/studios", headers=headers)
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "unauthorized"

    serve(tmp_path, monkeypatch, scenario, db=True)


# 10. 开发模拟认证


def test_dev_simulation_login_and_x_user_id(tmp_path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        body = await login_ok(client)
        assert body["user"]["user_id"] == "demo"

        # MVP 的 X-User-Id 开发模拟保持原行为
        created = await client.post("/api/v1/studios", json={"name": "Dev Studio", "business_type": "studio"}, headers={"X-User-Id": "alice"})
        assert created.status_code == 201
        listing = await client.get("/api/v1/studios", headers={"X-User-Id": "alice"})
        assert listing.status_code == 200
        missing = await client.get("/api/v1/studios")
        assert missing.status_code == 401
        assert missing.json() == {"error": {"code": "unauthorized", "message": "X-User-Id is required in development and test"}}

    serve(tmp_path, monkeypatch, scenario, db=True)


def test_dev_provider_refuses_production_settings() -> None:
    try:
        DevSimulatedIdentityProvider(Settings(environment="production"))
    except RuntimeError:
        return
    raise AssertionError("DevSimulatedIdentityProvider must refuse production settings")


# 11. 生产环境 503 安全门禁


def test_production_rejects_dev_credentials_and_spoofed_identity(tmp_path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        login = await client.post(LOGIN, json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
        me = await client.get(ME, headers=DEMO_HEADERS)
        logout = await client.post(LOGOUT, headers=DEMO_HEADERS)
        studios = await client.get("/api/v1/studios", headers={"X-User-Id": "alice"})
        for response in (login, me, logout, studios):
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "unauthorized"
            assert DEMO_PASSWORD not in response.text

    serve(tmp_path, monkeypatch, scenario, environment="production", db=True)


def test_production_cookie_csrf_roles_and_tenant_isolation(tmp_path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        alice = await client.post(LOGIN, json={"username": "alice", "password": "alice-long-password"})
        assert alice.status_code == 200
        assert alice.json()["user"]["username"] == "alice"
        assert "credential" not in alice.json()
        assert "HttpOnly" in alice.headers["set-cookie"]
        assert "Secure" in alice.headers["set-cookie"]
        assert (await client.get(ME)).status_code == 200
        csrf = client.cookies["lc_csrf"]
        body = {"name": "Alice Studio", "business_type": "studio"}
        assert (await client.post("/api/v1/studios", json=body)).status_code == 403
        created = await client.post("/api/v1/studios", json=body, headers={"X-CSRF-Token": csrf})
        assert created.status_code == 201
        studio_id = created.json()["id"]
        assert (await client.get(f"/api/v1/studios/{studio_id}", headers={"X-User-Id": "owner"})).status_code == 200

        bob = await client.post(LOGIN, json={"username": "bob", "password": "bob-long-password"})
        assert bob.status_code == 200
        assert (await client.get(f"/api/v1/studios/{studio_id}", headers={"X-User-Id": "alice"})).status_code == 404
        assert (await client.get("/api/v1/studios")).json() == []
        assert (await client.post("/api/v1/reports/unknown/publish",
                                  headers={"X-CSRF-Token": client.cookies["lc_csrf"]})).status_code == 403

        owner = await client.post(LOGIN, json={"username": "admin", "password": "admin-long-password"})
        assert owner.status_code == 200
        assert (await client.get(f"/api/v1/studios/{studio_id}")).status_code == 200
        assert (await client.post(LOGOUT)).status_code == 403
        assert (await client.post(LOGOUT, headers={"X-CSRF-Token": client.cookies["lc_csrf"]})).status_code == 200
        assert (await client.get(ME)).status_code == 401

    serve(tmp_path, monkeypatch, scenario, environment="production", db=True,
          seed_users=[("alice", "alice-long-password", "customer"),
                      ("bob", "bob-long-password", "customer"),
                      ("admin", "admin-long-password", "owner")])


def test_production_login_failure_limit(tmp_path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        for _ in range(5):
            bad = await client.post(LOGIN, json={"username": "alice", "password": "wrong-password"})
            assert bad.status_code == 401
        locked = await client.post(LOGIN, json={"username": "alice", "password": "alice-long-password"})
        assert locked.status_code == 401
        assert locked.json() == bad.json()

    serve(tmp_path, monkeypatch, scenario, environment="production", db=True,
          seed_users=[("alice", "alice-long-password", "customer")])


def test_local_session_expiry_and_revocation(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "expired-session.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    settings = Settings(environment="production", database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}")
    engine = make_engine(settings.database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def check() -> None:
        try:
            async with sessions() as db:
                await create_user(db, "alice", "alice-long-password")
            provider = LocalIdentityProvider(sessions, settings)
            first = await provider.login("alice", SecretStr("alice-long-password"))
            assert first is not None
            assert await provider.resolve(SCHEME, first.credential) is not None
            assert await provider.validate_csrf(first.credential, first.csrf_token or "")
            assert await provider.logout(SCHEME, first.credential)
            assert await provider.resolve(SCHEME, first.credential) is None
            second = await provider.login("alice", SecretStr("alice-long-password"))
            assert second is not None
            async with sessions() as db:
                row = await db.get(UserSession, hashlib.sha256(second.credential.encode()).hexdigest())
                assert row is not None
                row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                await db.commit()
            assert await provider.resolve(SCHEME, second.credential) is None
            assert not await provider.validate_csrf(second.credential, second.csrf_token or "")
        finally:
            await engine.dispose()

    asyncio.run(check())


# 12. 原有 MVP 权限回归（含凭据身份下的租户隔离）


def test_mvp_permissions_and_credential_identity_regression(tmp_path, monkeypatch) -> None:
    accounts = json.dumps([
        {"email": "alice@example.com", "user_id": "alice", "password": "alice-password"},
        {"email": "bob@example.com", "user_id": "bob", "password": "bob-password"},
    ])

    async def scenario(client: AsyncClient) -> None:
        created = await client.post(
            "/api/v1/studios",
            json={"name": "Alice Studio", "business_type": "studio"},
            headers={"X-User-Id": "alice"},
        )
        assert created.status_code == 201
        studio_id = created.json()["id"]

        alice = await login_ok(client, "alice@example.com", "alice-password")
        bob = await login_ok(client, "bob@example.com", "bob-password")

        own = await client.get(f"/api/v1/studios/{studio_id}", headers=auth_header(alice["credential"]["value"]))
        assert own.status_code == 200
        assert own.json()["owner_user_id"] == "alice"

        # 跨租户越权仍隐藏为 404（MVP 权限体系不被破坏）
        cross = await client.get(f"/api/v1/studios/{studio_id}", headers=auth_header(bob["credential"]["value"]))
        assert cross.status_code == 404
        spoofed = await client.get(f"/api/v1/studios/{studio_id}", headers={"X-User-Id": "bob"})
        assert spoofed.status_code == 404

    serve(tmp_path, monkeypatch, scenario, env={"DEV_AUTH_ACCOUNTS": accounts}, db=True)


# 防重复请求：重复登录不堆积有效认证状态


def test_duplicate_login_replaces_previous_credential(tmp_path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        first = await login_ok(client)
        second = await login_ok(client)
        assert first["credential"]["value"] != second["credential"]["value"]
        stale = await client.get(ME, headers=auth_header(first["credential"]["value"]))
        assert stale.status_code == 401
        fresh = await client.get(ME, headers=auth_header(second["credential"]["value"]))
        assert fresh.status_code == 200

    serve(tmp_path, monkeypatch, scenario)
